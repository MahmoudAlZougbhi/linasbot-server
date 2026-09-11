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


def _published_human_request_rule_enabled(sections: dict) -> bool | None:
    """True/False when Requests has HUMAN rules; None when the owner has not configured one."""
    raw = sections.get("requests_appointments") if isinstance(sections, dict) else None
    rules = raw.get("rules") if isinstance(raw, dict) else None
    if not isinstance(rules, list):
        return None
    human_rules = [
        rule for rule in rules if isinstance(rule, dict) and str(rule.get("type") or "").strip().upper() == "HUMAN"
    ]
    if not human_rules:
        return None
    return any(bool(rule.get("enabled", True)) for rule in human_rules)


def human_handoff_enabled(tenant_id: str) -> bool:
    """True when a published Requests HUMAN rule (or AI Limits fallback) allows handoff."""
    tid = (tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    if not tenant_uses_cm_runtime(tid):
        return True
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return True

    human_rule = _published_human_request_rule_enabled(sections)
    if human_rule is not None:
        return human_rule

    raw_limits = sections.get("ai_limits")
    if isinstance(raw_limits, dict) and "human_handoff_enabled" in raw_limits:
        return bool(raw_limits["human_handoff_enabled"])

    from services.cm.actions import ACTION_HUMAN_HANDOFF, action_enabled

    # Read the fallback from the same verified published snapshot as AI Limits.
    # Re-loading through actions.load_actions_section can observe another
    # pointer (and made this gate disagree with an otherwise valid snapshot).
    raw_actions = sections.get("actions")
    if raw_actions is not None:
        return action_enabled(raw_actions, ACTION_HUMAN_HANDOFF)

    limits = AiLimitsSection.model_validate(raw_limits or {})
    return bool(limits.human_handoff_enabled)
