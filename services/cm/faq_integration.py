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

    record = FaqRecord(qa_group_id=qa_group_id, variants=variants, tags=list(tags or []), notes=None)
    _mirror_faq_record_into_draft(record, tenant_id=tenant_id, updated_by=updated_by)

    return {
        "success": True,
        "qa_group_id": qa_group_id,
        "created_entries": created_entries,
        "count_created": len(created_entries),
        "detected_language": detected_language,
        "record": record.model_dump(mode="json"),
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


def list_cm_faq(*, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """List FAQ groups (metadata + variant preview) from the CM draft faq section."""
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    return [item.model_dump(mode="json") for item in section.items]
