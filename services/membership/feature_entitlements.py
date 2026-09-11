"""Server feature gates from the message catalog. Not a second price list."""

from __future__ import annotations

from typing import Any

from services.membership.message_catalog import MessagePlan, require_message_plan


class FeatureDenied(PermissionError):
    def __init__(self, code: str, message: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


def _plan(plan_id: str) -> MessagePlan | None:
    try:
        return require_message_plan(plan_id)
    except KeyError:
        return None


def additional_seats_for_plan(plan_id: str) -> tuple[bool, int | None]:
    plan = _plan(plan_id)
    if plan is None:
        return False, None
    return True, plan.additional_seats


def faq_limits_for_plan(plan_id: str) -> tuple[bool, int]:
    plan = _plan(plan_id)
    if plan is None or plan.plan_id == "free" or not plan.faq_enabled:
        return False, 0
    from services.membership.catalog_admin import effective_offer_fields

    return True, int(effective_offer_fields(plan_id).get("faq_capacity") or 0)


def followup_allowed_for_plan(plan_id: str) -> bool:
    plan = _plan(plan_id)
    return bool(plan is not None and plan.followup_enabled)


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
        "faq_enabled": bool(plan.faq_enabled),
        "followup_enabled": bool(plan.followup_enabled),
    }


def feature_gates_live() -> bool:
    """Catalog limits stay published; enforcement waits for billing or Free caps."""
    from services.membership.message_flags import free_enforcement_enabled, message_billing_enabled

    return message_billing_enabled() or free_enforcement_enabled()


def assert_followup_allowed(tenant_id: str) -> None:
    from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant

    if not feature_gates_live():
        return
    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    paid = ent.status in {"active", "trial", "grace"}
    if not paid or not followup_allowed_for_plan(ent.plan_id):
        raise FeatureDenied(
            "FOLLOWUP_DISABLED",
            "Smart Follow-Up is locked on this plan.",
            {"plan_id": ent.plan_id, "status": ent.status, "followup_enabled": False},
        )


def assert_comments_allowed(tenant_id: str) -> None:
    from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant

    if not feature_gates_live():
        return
    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    paid = ent.status in {"active", "trial", "grace"}
    if not paid or not comments_allowed_for_plan(ent.plan_id):
        raise FeatureDenied(
            "COMMENTS_DISABLED",
            "Comment automation is locked on this plan.",
            {"plan_id": ent.plan_id, "status": ent.status, "comment_automation": False},
        )
