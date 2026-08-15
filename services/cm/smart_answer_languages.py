"""Smart Answer language settings — separate from CM customer reply languages."""

from __future__ import annotations

from typing import Any

from services.cm.faq_integration_helpers import FAQ_SECTION, FaqIntegrationError
from services.cm.iso639_languages import iso639_catalog, iso639_label, iso639_native_label, normalize_language_code
from services.cm.schemas import FaqSection
from services.cm.storage import get_draft, put_draft

DEFAULT_SMART_ANSWER_LANGUAGES: tuple[str, ...] = ("ar", "en", "fr", "franco")


def normalize_smart_answer_language(code: str | None) -> str:
    return normalize_language_code(code)


def normalize_smart_answer_languages(codes: list[str] | tuple[str, ...] | None) -> list[str]:
    out: list[str] = []
    for code in codes or DEFAULT_SMART_ANSWER_LANGUAGES:
        normalized = normalize_smart_answer_language(code)
        if normalized and normalized not in out:
            out.append(normalized)
    return out or list(DEFAULT_SMART_ANSWER_LANGUAGES)


def _load_faq_section(*, tenant_id: str | None) -> FaqSection:
    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    return FaqSection.model_validate(env.payload)


def load_smart_answer_languages(*, tenant_id: str | None) -> list[str]:
    section = _load_faq_section(tenant_id=tenant_id)
    return normalize_smart_answer_languages(section.smart_answer_languages)


def smart_answer_languages_public(*, tenant_id: str | None) -> dict[str, Any]:
    selected = load_smart_answer_languages(tenant_id=tenant_id)
    return {
        "smart_answer_languages": selected,
        "catalog": iso639_catalog(),
        "default_languages": list(DEFAULT_SMART_ANSWER_LANGUAGES),
    }


def save_smart_answer_languages(
    *,
    tenant_id: str | None,
    languages: list[str],
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    normalized = normalize_smart_answer_languages(languages)
    if not normalized:
        raise FaqIntegrationError("At least one Smart Q&A language is required")

    env = get_draft(FAQ_SECTION, tenant_id=tenant_id, create_default=True)
    section = FaqSection.model_validate(env.payload)
    previous = normalize_smart_answer_languages(section.smart_answer_languages)
    added = [lang for lang in normalized if lang not in previous]
    removed = [lang for lang in previous if lang not in normalized]

    updated = FaqSection(
        items=section.items,
        notes=section.notes,
        smart_answer_languages=normalized,
    )
    put_draft(
        FAQ_SECTION,
        payload=updated.model_dump(mode="json"),
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by=updated_by,
    )
    return {
        "success": True,
        "smart_answer_languages": normalized,
        "added": added,
        "removed": removed,
    }


def remove_smart_answer_language(
    *,
    tenant_id: str | None,
    language: str,
    updated_by: str = "content_manager",
) -> dict[str, Any]:
    """Remove one Smart Q&A language from tenant config (does not purge FAQ rows)."""
    lang = normalize_smart_answer_language(language)
    if not lang:
        raise FaqIntegrationError(f"Unsupported Smart Q&A language: {language}")

    current = load_smart_answer_languages(tenant_id=tenant_id)
    if lang not in current:
        raise FaqIntegrationError(f"Language not configured: {lang}")
    if len(current) <= 1:
        raise FaqIntegrationError("At least one Smart Q&A language is required")

    next_langs = [code for code in current if code != lang]
    return save_smart_answer_languages(
        tenant_id=tenant_id,
        languages=next_langs,
        updated_by=updated_by,
    )


def language_display_name(code: str) -> str:
    return iso639_native_label(code) or iso639_label(code) or code
