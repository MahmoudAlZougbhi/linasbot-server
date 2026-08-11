"""CM FAQ draft list/get/update/regenerate ops (LOC split from faq_integration)."""

from __future__ import annotations

from typing import Any, cast

from services.cm.faq_integration_helpers import (
    FAQ_SECTION,
    FAQ_TARGET_LANGUAGES,
    FaqIntegrationError,
    _answer_in_arabic_script,
    _mirror_faq_record_into_draft,
    _translate_to_arabic_script,
)
from services.cm.schemas import FaqRecord, FaqSection, FaqVariant, LangCode
from services.cm.storage import get_draft, put_draft
from services.language_detection_service import language_detection_service
from services.local_qa_service import local_qa_service


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
        if not include_archived and item.status in {"archived", "restricted"}:
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
