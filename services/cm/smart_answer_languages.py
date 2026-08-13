"""Smart Answer language settings — separate from CM customer reply languages."""

from __future__ import annotations

from typing import Any

from services.cm.faq_integration_helpers import FAQ_SECTION, FaqIntegrationError
from services.cm.schemas import FaqSection
from services.cm.storage import get_draft, put_draft

DEFAULT_SMART_ANSWER_LANGUAGES: tuple[str, ...] = ("ar", "en", "fr", "franco")

# Catalog for owner language picker (design reference).
SMART_ANSWER_LANGUAGE_CATALOG: tuple[dict[str, str], ...] = (
    {"id": "en", "label": "English", "native": "English"},
    {"id": "ar", "label": "Arabic", "native": "العربية"},
    {"id": "franco", "label": "Franco / Arabizi", "native": "Franco"},
    {"id": "fr", "label": "French", "native": "Français"},
    {"id": "es", "label": "Spanish", "native": "Español"},
    {"id": "de", "label": "German", "native": "Deutsch"},
    {"id": "it", "label": "Italian", "native": "Italiano"},
    {"id": "pt", "label": "Portuguese", "native": "Português"},
    {"id": "zh", "label": "Chinese", "native": "中文"},
    {"id": "tr", "label": "Turkish", "native": "Türkçe"},
    {"id": "ru", "label": "Russian", "native": "Русский"},
)

_ALLOWED_SMART_ANSWER_IDS = frozenset(item["id"] for item in SMART_ANSWER_LANGUAGE_CATALOG)


def normalize_smart_answer_language(code: str | None) -> str:
    raw = str(code or "").strip().lower()
    aliases = {
        "arabic": "ar",
        "english": "en",
        "french": "fr",
        "franco-arabic": "franco",
        "franco_arabic": "franco",
        "arabizi": "franco",
        "spanish": "es",
        "german": "de",
        "italian": "it",
        "portuguese": "pt",
        "chinese": "zh",
        "turkish": "tr",
        "russian": "ru",
    }
    raw = aliases.get(raw, raw)
    if raw in _ALLOWED_SMART_ANSWER_IDS:
        return raw
    return ""


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
        "catalog": list(SMART_ANSWER_LANGUAGE_CATALOG),
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
        raise FaqIntegrationError("At least one Smart Answer language is required")

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
