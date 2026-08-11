"""Published AI Setup is the sole business source of truth for AI limits.

The enforcement JSON cache may be refreshed only by CM publish sync.
Settings UI must not write limits.
"""

from __future__ import annotations

from typing import Any

from services.ai_usage_limits import AiLimitSettings, ai_usage_limits_service, normalize_ai_limit_settings
from services.cm.schemas import AiLimitsSection


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
    return normalize_ai_limit_settings(
        {
            "unlimited": section.unlimited,
            "image_per_day": section.image_per_day,
            "image_per_week": section.image_per_week,
            "context_lines_per_day": section.context_lines_per_day,
            "context_lines_per_week": section.context_lines_per_week,
            "enforce_image_day": section.enforce_image_day,
            "enforce_image_week": section.enforce_image_week,
            "enforce_context_day": section.enforce_context_day,
            "enforce_context_week": section.enforce_context_week,
        }
    )


def get_ai_limits_for_api(tenant_id: str) -> dict[str, Any]:
    """Public read model: prefer published CM; otherwise report unpublished state."""
    published = limits_from_published(tenant_id)
    if published is not None:
        return {
            "source": "published_cm",
            "published": True,
            "limits": published.to_public_dict(),
        }
    cached = ai_usage_limits_service.get_settings(tenant_id)
    return {
        "source": "unpublished_cache",
        "published": False,
        "limits": cached.to_public_dict(),
        "message": "Publish AI Setup → AI Limits to make these active.",
    }
