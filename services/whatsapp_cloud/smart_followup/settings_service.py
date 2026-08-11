"""Settings validation + persistence for Smart Follow-Up."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from services.whatsapp_cloud.smart_followup.constants import (
    ALLOWED_BILLING_MODES,
    BILLING_MODE_CUSTOMER_DIRECT,
    GOALS,
    MAX_DELAY_MINUTES,
)
from services.whatsapp_cloud.smart_followup.repository import SmartFollowUpRepository


class SmartFollowUpSettingsError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(steps, list) or not (1 <= len(steps) <= 3):
        raise SmartFollowUpSettingsError("invalid_step_count", "Smart Follow-Up requires 1–3 steps")
    seen: set[int] = set()
    cleaned: list[dict[str, Any]] = []
    for raw in steps:
        if not isinstance(raw, dict):
            raise SmartFollowUpSettingsError("invalid_step", "Each step must be an object")
        try:
            raw_idx = raw.get("step_index")
            raw_delay = raw.get("delay_minutes")
            if raw_idx is None or raw_delay is None:
                raise TypeError("missing_step_fields")
            idx = int(raw_idx)
            delay = int(raw_delay)
        except (TypeError, ValueError) as exc:
            raise SmartFollowUpSettingsError(
                "invalid_step_fields", "step_index and delay_minutes must be integers"
            ) from exc
        goal = str(raw.get("goal") or "").strip()
        enabled = bool(raw.get("enabled", True))
        if idx < 1 or idx > 3:
            raise SmartFollowUpSettingsError("invalid_step_index", "step_index must be 1–3")
        if idx in seen:
            raise SmartFollowUpSettingsError("duplicate_step_index", "Duplicate step_index")
        seen.add(idx)
        if delay <= 0:
            raise SmartFollowUpSettingsError("invalid_delay", "delay_minutes must be positive")
        if delay > MAX_DELAY_MINUTES:
            raise SmartFollowUpSettingsError(
                "delay_exceeds_window",
                f"delay_minutes must be <= {MAX_DELAY_MINUTES} to fit Meta's customer-service window",
            )
        if goal not in GOALS:
            raise SmartFollowUpSettingsError("invalid_goal", f"Unsupported goal: {goal}")
        cleaned.append(
            {
                "step_index": idx,
                "enabled": enabled,
                "delay_minutes": delay,
                "goal": goal,
            }
        )
    cleaned.sort(key=lambda s: int(s["step_index"]))
    # Absolute delays: each enabled step delay is from trigger, not cumulative.
    # Require strictly increasing delays among enabled steps for sane UX.
    prev = 0
    for step in cleaned:
        if not step["enabled"]:
            continue
        if int(step["delay_minutes"]) <= prev:
            raise SmartFollowUpSettingsError(
                "delays_not_increasing",
                "Enabled step delays must be strictly increasing (absolute from AI reply)",
            )
        prev = int(step["delay_minutes"])
    if not any(s["enabled"] for s in cleaned):
        raise SmartFollowUpSettingsError("no_enabled_steps", "At least one step must be enabled")
    return cleaned


def settings_public_view(
    settings: Any,
    steps: list[Any],
    *,
    blockers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "feature": "smart_followup",
        "feature_ar": "المتابعة الذكية",
        "enabled": bool(settings.enabled),
        "business_hours_only": bool(settings.business_hours_only),
        "billing_mode": str(settings.billing_mode or BILLING_MODE_CUSTOMER_DIRECT),
        "billing_manage_in_meta": settings.billing_mode == BILLING_MODE_CUSTOMER_DIRECT,
        "settings_version": int(settings.settings_version),
        "updated_at": settings.updated_at.isoformat() if getattr(settings, "updated_at", None) else None,
        "steps": [
            {
                "step_index": int(s.step_index),
                "enabled": bool(s.enabled),
                "delay_minutes": int(s.delay_minutes),
                "goal": str(s.goal),
            }
            for s in steps
        ],
        "stop_rules": [
            "customer_reply",
            "business_app_manual_reply",
            "conversation_paused",
            "feature_disabled",
            "ai_disabled",
            "whatsapp_disconnected",
            "opt_out",
            "insufficient_credits",
            "customer_service_window_expired",
        ],
        "message_policy": {
            "writer": "customer_reply_v2",
            "absolute_delays": True,
            "templates_customer_facing": False,
            "marketing_forbidden": True,
        },
        "blockers": blockers or {},
    }


def get_or_create_settings(session: Session, tenant_id: str) -> dict[str, Any]:
    repo = SmartFollowUpRepository(session)
    settings, steps = repo.ensure_defaults(tenant_id)
    return settings_public_view(settings, steps)


def update_settings(
    session: Session,
    *,
    tenant_id: str,
    actor_user_id: str,
    payload: dict[str, Any],
    expected_version: int | None = None,
) -> dict[str, Any]:
    repo = SmartFollowUpRepository(session)
    settings, _existing = repo.ensure_defaults(tenant_id)

    if expected_version is not None and int(settings.settings_version) != int(expected_version):
        raise SmartFollowUpSettingsError(
            "version_conflict",
            "Settings were updated elsewhere — reload and retry",
        )

    if "steps" in payload:
        cleaned = _validate_steps(list(payload.get("steps") or []))
        repo.replace_steps(settings=settings, steps_payload=cleaned)

    if "enabled" in payload:
        settings.enabled = bool(payload["enabled"])
    if "business_hours_only" in payload:
        settings.business_hours_only = bool(payload["business_hours_only"])
    if "billing_mode" in payload:
        mode = str(payload["billing_mode"]).strip()
        if mode not in ALLOWED_BILLING_MODES:
            raise SmartFollowUpSettingsError("invalid_billing_mode", "Unsupported billing_mode")
        # solution_partner reserved for later — refuse enabling it in this release.
        if mode == "solution_partner":
            raise SmartFollowUpSettingsError(
                "solution_partner_not_available",
                "Solution Partner billing is not available in this release",
            )
        settings.billing_mode = mode

    was_enabled = bool(settings.enabled)
    settings.updated_by_user_id = actor_user_id
    settings.settings_version = int(settings.settings_version) + 1
    session.flush()

    if was_enabled is False or settings.enabled is False:
        # Turning OFF invalidates queued jobs immediately.
        if not settings.enabled:
            repo.cancel_active_for_tenant(tenant_id=tenant_id, reason="feature_disabled")

    repo.record_event(
        tenant_id=tenant_id,
        event_type="settings_updated",
        detail={
            "enabled": settings.enabled,
            "business_hours_only": settings.business_hours_only,
            "settings_version": settings.settings_version,
            "actor_user_id": actor_user_id,
        },
    )
    steps = repo.list_steps(settings.id)
    return settings_public_view(settings, steps)
