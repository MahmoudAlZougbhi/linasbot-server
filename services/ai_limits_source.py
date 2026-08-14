"""CM ai_limits is the owner source of truth; enforcement JSON is the live cache.

The cache is refreshed on draft save (changes apply immediately) and on publish.
Settings POST must not write limits.
"""

from __future__ import annotations

from typing import Any

from services.ai_usage_limits import AiLimitSettings, ai_usage_limits_service, normalize_ai_limit_settings
from services.cm.schemas import AiLimitsSection


def section_to_enforcement_updates(section: AiLimitsSection) -> dict[str, Any]:
    return {
        # The Customer AI Limits screen no longer exposes an unlimited toggle.
        "unlimited": False,
        "image_per_day": section.image_per_day,
        "image_per_week": section.image_per_week,
        "image_per_month": section.image_per_month,
        "photos_per_message": section.photos_per_message,
        "text_words_per_message": section.text_words_per_message,
        "text_replies_per_day": section.text_replies_per_day,
        "text_replies_per_week": section.text_replies_per_week,
        "text_replies_per_month": section.text_replies_per_month,
        "voice_minutes_per_message": section.voice_minutes_per_message,
        "voice_minutes_per_day": section.voice_minutes_per_day,
        "voice_minutes_per_week": section.voice_minutes_per_week,
        "voice_minutes_per_month": section.voice_minutes_per_month,
        "context_lines_per_day": section.context_lines_per_day,
        "context_lines_per_week": section.context_lines_per_week,
        "enforce_image_day": section.enforce_image_day,
        "enforce_image_week": section.enforce_image_week,
        "enforce_image_month": section.enforce_image_month,
        "enforce_context_day": section.enforce_context_day,
        "enforce_context_week": section.enforce_context_week,
    }


def sync_enforcement_from_payload(tenant_id: str, payload: dict[str, object] | None) -> None:
    """Push CM ai_limits into the per-tenant enforcement JSON store."""
    limits = AiLimitsSection.model_validate(payload or {})
    ai_usage_limits_service.save_settings(tenant_id, section_to_enforcement_updates(limits))


def _published_ai_limits_section(tenant_id: str) -> AiLimitsSection | None:
    try:
        from services.cm.version_store import PublishedVersionError, load_published_content

        _pointer, sections = load_published_content(tenant_id)
        raw = sections.get("ai_limits")
        if not isinstance(raw, dict):
            return None
        return AiLimitsSection.model_validate(raw)
    except PublishedVersionError:
        return None
    except Exception:
        return None


def limits_from_published(tenant_id: str) -> AiLimitSettings | None:
    """Load quota settings from published CM, or None if unpublished/missing."""
    section = _published_ai_limits_section(tenant_id)
    if section is None:
        return None
    return normalize_ai_limit_settings(section_to_enforcement_updates(section))


def get_ai_limits_for_api(tenant_id: str) -> dict[str, Any]:
    """Public read model: live enforcement cache after save; published when present."""
    published = limits_from_published(tenant_id)
    cached = ai_usage_limits_service.get_settings(tenant_id)
    if published is not None:
        return {
            "source": "published_cm",
            "published": True,
            "limits": cached.to_public_dict(),
        }
    return {
        "source": "enforcement_cache",
        "published": False,
        "limits": cached.to_public_dict(),
        "message": "Save Customer AI Limits to apply immediately. Publish AI Setup to pin a version.",
    }
