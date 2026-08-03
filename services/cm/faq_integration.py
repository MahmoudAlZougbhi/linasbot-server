"""Bridge between CM FAQ drafts and the existing LocalQAService JSONL store (plan §8).

Actual Q&A rows stay in ``qa_pairs.jsonl`` via :mod:`services.local_qa_service` for full
compatibility with the existing bot-matching path. The CM ``faq`` draft section only tracks
group metadata (qa_group_id + a variant preview + tags/notes) so Content Managers can author
and audit FAQ without a second, divergent Q&A store.

Preserves the frozen contract (plan §2.4/§8): 4 linked variants per group; Franco question
stays Franco (Latin) while its answer is always Arabic script, same as the AR answer.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, cast

from services.cm.schemas import FaqRecord, FaqSection, FaqVariant, LangCode
from services.cm.storage import ConflictError, get_draft, put_draft
from services.language_detection_service import language_detection_service
from services.local_qa_service import local_qa_service

FAQ_SECTION = "faq"
FAQ_TARGET_LANGUAGES = ("ar", "en", "fr", "franco")
_MAX_MIRROR_RETRIES = 5


class FaqIntegrationError(RuntimeError):
    code: str = "FAQ_INTEGRATION_ERROR"


def _answer_in_arabic_script(text: str | None) -> bool:
    return bool(re.search(r"[\u0600-\u06FF]", text or ""))


async def _translate_to_arabic_script(text: str, source_language: str) -> str:
    """Translate a single text to Arabic script; returns input unchanged if already Arabic."""
    if not text or _answer_in_arabic_script(text):
        return text or ""
    result = await language_detection_service.translate_training_pair(
        question=text, answer=text, source_language=source_language, target_languages=["ar"]
    )
    ar_translation = result.get("translations", {}).get("ar", {})
    out = ar_translation.get("answer") or ar_translation.get("question") or ""
    return out if out and _answer_in_arabic_script(out) else text


def _build_entry(
    question: str,
    answer: str,
    language: str,
    category: str,
    qa_group_id: str,
    source_language: str,
    is_auto_translated: bool,
) -> dict[str, Any]:
    return {
        "question": question,
        "answer": answer,
        "language": language_detection_service.normalize_training_language(language),
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "qa_group_id": qa_group_id,
        "source_language": language_detection_service.normalize_training_language(source_language),
        "is_auto_translated": bool(is_auto_translated),
    }


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
        target_languages=list(FAQ_TARGET_LANGUAGES),
    )
    if not translation_result.get("success"):
        raise FaqIntegrationError("Failed to auto-translate FAQ pair to all 4 languages")

    translations = translation_result.get("translations", {})
    qa_group_id = f"qa_{uuid.uuid4().hex[:10]}"
    created_entries: list[dict[str, Any]] = []
    variants: list[FaqVariant] = []

    for lang in FAQ_TARGET_LANGUAGES:
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
            _build_entry(q_text, a_text, lang, category, qa_group_id, detected_language, lang != detected_language)
        )
        variants.append(FaqVariant(language=cast(LangCode, lang), question=q_text, answer=a_text))

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
        source_language=cast(LangCode, detected_language),
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
        "incomplete": not record.is_complete_four_lang,
    }


def _mirror_faq_record_into_draft(record: FaqRecord, *, tenant_id: str | None, updated_by: str) -> FaqSection:
    """Append/replace the FAQ group metadata in the CM 'faq' draft (optimistic-concurrency retry)."""
    last_error: ConflictError | None = None
    for _ in range(_MAX_MIRROR_RETRIES):
        env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
        section = FaqSection.model_validate(env.payload)
        items = [item for item in section.items if item.qa_group_id != record.qa_group_id]
        items.append(record)
        new_section = FaqSection(items=items, notes=section.notes)
        try:
            updated_env = put_draft(
                FAQ_SECTION,
                payload=new_section.model_dump(mode="json"),
                if_match=env.etag,
                tenant_id=tenant_id,
                updated_by=updated_by,
            )
            return FaqSection.model_validate(updated_env.payload)
        except ConflictError as exc:
            last_error = exc
            continue
    raise FaqIntegrationError(f"Could not mirror FAQ group into draft after retries: {last_error}")


def list_cm_faq(
    *,
    tenant_id: str | None = None,
    status: str | None = None,
    language: str | None = None,
    q: str | None = None,
    reviewed: bool | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List FAQ groups from the CM draft faq section with owner-friendly filters."""
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    query = (q or "").strip().lower()
    out: list[dict[str, Any]] = []
    for item in section.items:
        if not include_archived and item.status == "archived":
            continue
        if status and item.status != status:
            continue
        if reviewed is not None and bool(item.reviewed) != reviewed:
            continue
        if language:
            langs = {v.language for v in item.variants}
            if language not in langs:
                continue
        if query:
            blob = " ".join(
                [
                    item.qa_group_id,
                    " ".join(item.tags),
                    item.notes or "",
                    *[f"{v.question} {v.answer}" for v in item.variants],
                ]
            ).lower()
            if query not in blob:
                continue
        payload = item.model_dump(mode="json")
        payload["incomplete"] = not item.is_complete_four_lang
        out.append(payload)
    return out


def get_cm_faq_group(*, qa_group_id: str, tenant_id: str | None = None) -> dict[str, Any] | None:
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    for item in section.items:
        if item.qa_group_id == qa_group_id:
            payload = item.model_dump(mode="json")
            payload["incomplete"] = not item.is_complete_four_lang
            return payload
    return None


def archive_cm_faq_group(
    *,
    qa_group_id: str,
    tenant_id: str | None = None,
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    found: FaqRecord | None = None
    items: list[FaqRecord] = []
    for item in section.items:
        if item.qa_group_id == qa_group_id:
            found = item.model_copy(update={"status": "archived", "revision": item.revision + 1})
            items.append(found)
        else:
            items.append(item)
    if found is None:
        raise FaqIntegrationError(f"FAQ group not found: {qa_group_id}")
    put_draft(
        FAQ_SECTION,
        payload=FaqSection(items=items, notes=section.notes).model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    # Soft-deactivate matching local QA rows (preserve history; do not delete).
    deactivated = 0
    for pair in local_qa_service.qa_pairs:
        if pair.get("qa_group_id") == qa_group_id and pair.get("is_active", True):
            pair["is_active"] = False
            pair["status"] = "archived"
            deactivated += 1
    if deactivated:
        local_qa_service.save_to_jsonl()
    return {"success": True, "qa_group_id": qa_group_id, "status": "archived", "deactivated_rows": deactivated}


async def update_cm_faq_variant(
    *,
    qa_group_id: str,
    language: str,
    question: str | None = None,
    answer: str | None = None,
    reviewed: bool | None = None,
    tenant_id: str | None = None,
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    """Manually correct one language variant; does not invent missing facts."""
    lang = language_detection_service.normalize_training_language(language)
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    target: FaqRecord | None = None
    items: list[FaqRecord] = []
    for item in section.items:
        if item.qa_group_id != qa_group_id:
            items.append(item)
            continue
        variants: list[FaqVariant] = []
        hit = False
        for variant in item.variants:
            if variant.language != lang:
                variants.append(variant)
                continue
            hit = True
            new_q = question if question is not None else variant.question
            new_a = answer if answer is not None else variant.answer
            if lang in ("ar", "franco") and new_a and not _answer_in_arabic_script(new_a):
                raise FaqIntegrationError("AR/Franco answers must be Arabic script")
            variants.append(
                variant.model_copy(
                    update={
                        "question": new_q,
                        "answer": new_a,
                        "reviewed": bool(reviewed) if reviewed is not None else variant.reviewed,
                        "is_auto_translated": False
                        if question is not None or answer is not None
                        else variant.is_auto_translated,
                    }
                )
            )
        if not hit:
            raise FaqIntegrationError(f"Variant {lang} missing on group {qa_group_id}")
        target = item.model_copy(
            update={
                "variants": variants,
                "revision": item.revision + 1,
                "reviewed": bool(reviewed) if reviewed is not None else item.reviewed,
            }
        )
        items.append(target)
    if target is None:
        raise FaqIntegrationError(f"FAQ group not found: {qa_group_id}")
    put_draft(
        FAQ_SECTION,
        payload=FaqSection(items=items, notes=section.notes).model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    # Mirror manual correction into local QA store for runtime exact match.
    for pair in local_qa_service.qa_pairs:
        if pair.get("qa_group_id") == qa_group_id and pair.get("language") == lang:
            if question is not None:
                pair["question"] = question
            if answer is not None:
                pair["answer"] = answer
    local_qa_service.save_to_jsonl()
    payload = target.model_dump(mode="json")
    payload["incomplete"] = not target.is_complete_four_lang
    return {"success": True, "record": payload}


async def regenerate_cm_faq_variants(
    *,
    qa_group_id: str,
    source_language: str | None = None,
    languages: list[str] | None = None,
    tenant_id: str | None = None,
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    """Regenerate selected (or missing) variants from the source language pair."""
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    record = next((item for item in section.items if item.qa_group_id == qa_group_id), None)
    if record is None:
        raise FaqIntegrationError(f"FAQ group not found: {qa_group_id}")

    src_lang = language_detection_service.normalize_training_language(source_language or record.source_language or "ar")
    src_variant = next((v for v in record.variants if v.language == src_lang), None)
    if src_variant is None or not src_variant.question or not src_variant.answer:
        raise FaqIntegrationError("Source language variant is incomplete; cannot regenerate")

    targets = languages or list(FAQ_TARGET_LANGUAGES)
    translation_result = await language_detection_service.translate_training_pair(
        question=src_variant.question,
        answer=src_variant.answer if _answer_in_arabic_script(src_variant.answer) else src_variant.answer,
        source_language=src_lang,
        target_languages=targets,
    )
    if not translation_result.get("success"):
        raise FaqIntegrationError("Translation failed — retry; nothing was saved as success")

    answer_ar = src_variant.answer
    if not _answer_in_arabic_script(answer_ar):
        answer_ar = await _translate_to_arabic_script(src_variant.answer, src_lang)
        if not _answer_in_arabic_script(answer_ar):
            raise FaqIntegrationError("Could not produce Arabic-script answer for AR/Franco")

    translations = translation_result.get("translations", {})
    by_lang = {v.language: v for v in record.variants}
    for lang in targets:
        translated = translations.get(lang, {})
        q_text = translated.get("question", "") or (src_variant.question if lang == src_lang else "")
        a_text = answer_ar if lang in ("ar", "franco") else (translated.get("answer", "") or "")
        if not q_text or not a_text:
            continue
        by_lang[cast(LangCode, lang)] = FaqVariant(
            language=cast(LangCode, lang),
            question=q_text,
            answer=a_text,
            reviewed=False,
            is_auto_translated=lang != src_lang,
        )

    updated = record.model_copy(
        update={
            "variants": list(by_lang.values()),
            "revision": record.revision + 1,
            "source_language": cast(LangCode, src_lang),
            "status": "draft" if len(by_lang) < 4 else record.status,
        }
    )
    _mirror_faq_record_into_draft(updated, tenant_id=tenant_id, updated_by=updated_by)
    payload = updated.model_dump(mode="json")
    payload["incomplete"] = not updated.is_complete_four_lang
    return {"success": True, "record": payload}


def find_duplicate_faq_groups(
    *,
    question: str,
    language: str = "ar",
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    """Exact-normalized duplicate detection against CM FAQ draft (no silent merge)."""
    needle = " ".join((question or "").lower().split())
    if not needle:
        return []
    hits: list[dict[str, Any]] = []
    for item in list_cm_faq(tenant_id=tenant_id, include_archived=False):
        for variant in item.get("variants") or []:
            if language and variant.get("language") != language:
                continue
            hay = " ".join(str(variant.get("question") or "").lower().split())
            if hay == needle:
                hits.append(
                    {
                        "qa_group_id": item.get("qa_group_id"),
                        "language": variant.get("language"),
                        "question": variant.get("question"),
                        "answer": variant.get("answer"),
                        "status": item.get("status"),
                    }
                )
    return hits


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
