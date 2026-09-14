"""Server feature gates from the credit plan catalog. Not a second price list."""

from __future__ import annotations

from typing import Any

from services.billing.membership.plan_catalog import PLAN_CATALOG, PlanDefinition


class FeatureDenied(PermissionError):
    def __init__(self, code: str, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


def _plan(plan_id: str) -> PlanDefinition | None:
    pid = (plan_id or "").strip().lower()
    return PLAN_CATALOG.get(pid)


def additional_seats_for_plan(plan_id: str) -> tuple[bool, int | None]:
    plan = _plan(plan_id)
    if plan is None:
        return False, None
    return True, plan.additional_seats


def faq_limits_for_plan(plan_id: str) -> tuple[bool, int]:
    plan = _plan(plan_id)
    if plan is None:
        return False, 0
    return True, int(plan.faq_capacity)


def followup_allowed_for_plan(plan_id: str) -> bool:
    plan = _plan(plan_id)
    return bool(plan is not None)


def comments_allowed_for_plan(plan_id: str) -> bool:
    plan = _plan(plan_id)
    return bool(plan is not None and plan.comment_automation)


def whatsapp_allowed_for_plan(plan_id: str) -> bool:
    plan = _plan(plan_id)
    return bool(plan is not None and plan.whatsapp)


def web_allowed_for_plan(plan_id: str) -> bool:
    plan = _plan(plan_id)
    return bool(plan is not None and plan.web)


def tiktok_allowed_for_plan(plan_id: str) -> bool:
    plan = _plan(plan_id)
    return bool(plan is not None and plan.tiktok)


def channel_flags_for_plan(plan_id: str) -> dict[str, bool]:
    plan = _plan(plan_id)
    if plan is None:
        return {}
    return {
        "comment_automation": bool(plan.comment_automation),
        "whatsapp": bool(plan.whatsapp),
        "web": bool(plan.web),
        "tiktok": bool(plan.tiktok),
        "faq_enabled": True,
        "followup_enabled": True,
    }


def feature_gates_live() -> bool:
    """Catalog limits stay published; enforcement is not a second billing meter."""
    return False


def assert_followup_allowed(tenant_id: str) -> None:
    _ = tenant_id
    return


def assert_comments_allowed(tenant_id: str) -> None:
    _ = tenant_id
    return
