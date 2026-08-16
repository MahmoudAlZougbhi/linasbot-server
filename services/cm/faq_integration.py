"""Bridge between CM FAQ drafts and the existing LocalQAService JSONL store (plan §8).

Actual Q&A rows stay in ``qa_pairs.jsonl`` via :mod:`services.local_qa_service` for full
compatibility with the existing bot-matching path. The CM ``faq`` draft section only tracks
group metadata (qa_group_id + a variant preview + tags/notes) so AI Setup can author
and audit FAQ without a second, divergent Q&A store.

Preserves Smart Answer groups with per-tenant ``smart_answer_languages`` (not always 4).
Franco question stays Franco (Latin) while its answer is always Arabic script, same as the AR answer.

Helpers/ops: faq_integration_helpers, faq_integration_ops (LOC split).
"""

from __future__ import annotations

import uuid
from typing import Any

from services.cm.faq_integration_helpers import (  # noqa: F401
    FAQ_SECTION,
    FAQ_TARGET_LANGUAGES,
    FaqIntegrationError,
    _answer_in_arabic_script,
    _build_entry,
    _mirror_faq_record_into_draft,
    _translate_to_arabic_script,
    load_faq_target_languages,
)
from services.cm.faq_integration_ops import (  # noqa: F401
    archive_cm_faq_group,
    find_duplicate_faq_groups,
    get_cm_faq_group,
    list_cm_faq,
    purge_smart_answer_language_data,
    regenerate_cm_faq_variants,
    replace_cm_faq_attachments,
    translate_existing_faq_groups_to_language,
    update_cm_faq_variant,
)
from services.cm.schemas import FaqRecord, FaqSection, FaqVariant
from services.cm.storage import get_draft, put_draft
from services.language_detection_service import language_detection_service
from services.local_qa_service import local_qa_service


async def create_faq_pair(
    *,
    question: str,
    answer: str,
    language: str = "ar",
    category: str = "content_manager",
    tags: list[str] | None = None,
    tenant_id: str | None = None,
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    """Create a 4-language FAQ pair via LocalQAService and mirror its metadata into CM draft.

    Answer rule (frozen): AR and Franco rows always carry an Arabic-script answer.
    """
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        raise FaqIntegrationError("Question and answer are required")
    if tenant_id:
        from services.faq_entitlements import FaqEntitlementError, assert_can_create_faq

        try:
            assert_can_create_faq(str(tenant_id))
        except FaqEntitlementError as exc:
            raise FaqIntegrationError(str(exc)) from exc

    detected_language = language_detection_service.normalize_training_language(
        language,
        default=language_detection_service.detect_training_language(question),
    )

    answer_ar_canonical = answer
    if not _answer_in_arabic_script(answer_ar_canonical):
        answer_ar_canonical = await _translate_to_arabic_script(answer, detected_language)
        if not _answer_in_arabic_script(answer_ar_canonical):
            answer_ar_canonical = await _translate_to_arabic_script(answer, "franco")
        if not _answer_in_arabic_script(answer_ar_canonical):
            answer_ar_canonical = answer  # translation failed; keep original rather than invent text

    translation_result = await language_detection_service.translate_training_pair(
        question=question,
        answer=answer_ar_canonical,
        source_language=detected_language,
        target_languages=load_faq_target_languages(tenant_id=tenant_id),
    )
    if not translation_result.get("success"):
        raise FaqIntegrationError("Failed to auto-translate FAQ pair to all 4 languages")

    translations = translation_result.get("translations", {})
    qa_group_id = f"qa_{uuid.uuid4().hex[:10]}"
    target_langs = load_faq_target_languages(tenant_id=tenant_id)
    created_entries: list[dict[str, Any]] = []
    variants: list[FaqVariant] = []

    for lang in target_langs:
        translated = translations.get(lang, {})
        q_text = translated.get("question", "") or question
        a_text = (
            answer_ar_canonical if lang in ("ar", "franco") else (translated.get("answer", "") or answer_ar_canonical)
        )

        if lang == "ar" and q_text and not _answer_in_arabic_script(q_text):
            q_text = await _translate_to_arabic_script(q_text, detected_language)
            if not _answer_in_arabic_script(q_text):
                q_text = await _translate_to_arabic_script(q_text, "franco")
        if lang == "franco" and (not q_text or _answer_in_arabic_script(q_text)):
            franco_translated = translations.get("franco", {})
            q_text = franco_translated.get("question", "") or (question if detected_language == "franco" else "")
        if not q_text or not a_text:
            continue
        if lang == "ar" and not _answer_in_arabic_script(q_text):
            continue  # never store an AR row with Franco-script question

        created_entries.append(
            _build_entry(
                q_text,
                a_text,
                lang,
                category,
                qa_group_id,
                detected_language,
                lang != detected_language,
                tenant_id=tenant_id,
            )
        )
        variants.append(FaqVariant(language=lang, question=q_text, answer=a_text))

    if not created_entries:
        raise FaqIntegrationError("No FAQ variants could be created")

    local_qa_service.qa_pairs.extend(created_entries)
    if not local_qa_service.save_to_jsonl():
        for _ in created_entries:
            local_qa_service.qa_pairs.pop()
        raise FaqIntegrationError("Failed to write FAQ pair to qa_pairs.jsonl")

    record = FaqRecord(
        qa_group_id=qa_group_id,
        variants=variants,
        tags=list(tags or []),
        notes=None,
        status="draft",
        source_language=detected_language,
        reviewed=False,
        provenance=f"cm_faq:{category}",
        revision=1,
    )
    _mirror_faq_record_into_draft(record, tenant_id=tenant_id, updated_by=updated_by)

    return {
        "success": True,
        "qa_group_id": qa_group_id,
        "created_entries": created_entries,
        "count_created": len(created_entries),
        "detected_language": detected_language,
        "record": record.model_dump(mode="json"),
        "incomplete": not record.is_complete_for_languages(target_langs),
    }


async def create_faq_pair_from_livechat(
    *,
    question: str,
    answer: str,
    language: str = "ar",
    updated_by: str = "live_chat",
    tenant_id: str | None = None,
    publish: bool = False,
) -> dict[str, Any]:
    """Canonical Live Chat Like → FAQ writer. Never writes remote/dead QA stores."""
    duplicates = find_duplicate_faq_groups(question=question, language=language, tenant_id=tenant_id)
    result = await create_faq_pair(
        question=question,
        answer=answer,
        language=language,
        category="operator_trained",
        tags=["operator_trained", "save_to_faq", "live_chat"],
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    result["duplicates"] = duplicates
    result["published"] = False
    if publish:
        # Mark group active in draft; atomic FAQ-only publish is handled by publish API separately.
        group = get_cm_faq_group(qa_group_id=result["qa_group_id"], tenant_id=tenant_id)
        if group:
            env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
            section = FaqSection.model_validate(env.payload)
            items = []
            for item in section.items:
                if item.qa_group_id == result["qa_group_id"]:
                    items.append(item.model_copy(update={"status": "active"}))
                else:
                    items.append(item)
            put_draft(
                FAQ_SECTION,
                payload=FaqSection(items=items, notes=section.notes).model_dump(mode="json"),
                if_match=env.etag,
                tenant_id=tenant_id,
                updated_by=updated_by,
            )
            result["published"] = False  # still requires CM publish for immutable version
            result["awaiting_publication"] = True
            result["status"] = "active"
    else:
        result["awaiting_publication"] = True
        result["status"] = "draft"
    return result
