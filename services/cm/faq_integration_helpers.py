"""Shared helpers/constants for CM FAQ integration (LOC split)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from services.cm.schemas import FaqRecord, FaqSection
from services.cm.storage import ConflictError, get_draft, put_draft
from services.language_detection_service import language_detection_service

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
    tenant_id: str | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "question": question,
        "answer": answer,
        "language": language_detection_service.normalize_training_language(language),
        "category": category,
        "timestamp": datetime.now().isoformat(),
        "qa_group_id": qa_group_id,
        "source_language": language_detection_service.normalize_training_language(source_language),
        "is_auto_translated": bool(is_auto_translated),
        "is_active": True,
        "status": "active",
    }
    if tenant_id:
        entry["tenant_id"] = str(tenant_id).strip().lower()
    return entry


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
