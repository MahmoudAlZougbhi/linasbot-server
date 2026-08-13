"""Published CM capability gates for voice/image processing (AI Limits SoT)."""

from __future__ import annotations

from services.cm.constants import tenant_uses_cm_runtime
from services.cm.schemas import AiLimitsSection
from services.cm.version_store import PublishedVersionError, load_published_content


def _load_ai_limits(tenant_id: str) -> AiLimitsSection | None:
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    if not tenant_uses_cm_runtime(tid):
        return None
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return None
    return AiLimitsSection.model_validate(sections.get("ai_limits") or {})


def voice_processing_enabled(tenant_id: str) -> bool:
    """True when published AI Limits enable voice processing (default True)."""
    limits = _load_ai_limits(tenant_id)
    if limits is None:
        # Unpublished / no CM runtime: keep existing Linas ops behavior.
        return True
    return bool(limits.voice_processing_enabled)


def image_analysis_enabled(tenant_id: str) -> bool:
    """True when published AI Limits enable image analysis (default True)."""
    limits = _load_ai_limits(tenant_id)
    if limits is None:
        return True
    return bool(limits.image_analysis_enabled)


def human_handoff_enabled(tenant_id: str) -> bool:
    """True when published AI Limits enable human handoff (falls back to legacy actions toggle)."""
    limits = _load_ai_limits(tenant_id)
    if limits is None:
        return True
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        sections = {}
    raw_limits = sections.get("ai_limits") or {}
    if isinstance(raw_limits, dict) and "human_handoff_enabled" in raw_limits:
        return bool(raw_limits["human_handoff_enabled"])
    from services.cm.actions import ACTION_HUMAN_HANDOFF, action_enabled, load_actions_section

    actions = load_actions_section(tenant_id)
    if actions is not None:
        return action_enabled(actions, ACTION_HUMAN_HANDOFF)
    return bool(limits.human_handoff_enabled)
