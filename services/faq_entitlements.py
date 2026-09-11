"""FAQ / Smart Answers entitlements from the message catalog.

Source of truth: ``services.membership.message_catalog`` via ``faq_limits_for_plan``.
Published catalog overlays apply after admin publish. Quota counts CM FAQ groups.
"""

from __future__ import annotations

from typing import Any

from services.membership.feature_entitlements import faq_limits_for_plan
from services.membership.message_catalog import PUBLIC_PAID_PLAN_IDS


class FaqEntitlementError(PermissionError):
    """Raised when FAQ is disabled or at quota for the tenant plan."""

    def __init__(self, message: str, *, code: str, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = payload or {}


def _plan_faq_limits(plan_id: str) -> tuple[bool, int]:
    return faq_limits_for_plan(plan_id)


def count_faq_entries(tenant_id: str) -> int:
    """Count non-archived FAQ groups for the tenant (CM draft is source of truth)."""
    from services.cm.faq_integration import list_cm_faq

    items = list_cm_faq(tenant_id=tenant_id, include_archived=False)
    return len(items)


def get_faq_entitlement(tenant_id: str) -> dict[str, Any]:
    from services.entitlements_service import entitlements_store

    ent = entitlements_store.get(tenant_id)
    paid_active = ent.status in {"active", "trial", "grace"} and ent.plan_id in PUBLIC_PAID_PLAN_IDS
    enabled, max_entries = _plan_faq_limits(ent.plan_id if paid_active else "none")
    if not paid_active:
        enabled, max_entries = False, 0
    used = count_faq_entries(tenant_id) if enabled or max_entries else count_faq_entries(tenant_id)
    remaining = max(0, max_entries - used) if enabled else 0
    at_limit = enabled and used >= max_entries
    return {
        "tenant_id": tenant_id,
        "plan_id": ent.plan_id,
        "status": ent.status,
        "faq_enabled": enabled,
        "faq_max_entries": max_entries,
        "faq_used_entries": used,
        "faq_remaining_entries": remaining,
        "at_limit": at_limit,
        "quota_display": f"{used} / {max_entries}" if enabled else "0 / 0",
        "upgrade_message": (
            None
            if enabled and not at_limit
            else (
                "Smart Q&A is not included on your current plan. Upgrade to enable FAQ."
                if not enabled
                else (f"Smart Q&A quota reached ({used} / {max_entries}). Upgrade your plan for a higher FAQ limit.")
            )
        ),
    }


def assert_can_create_faq(tenant_id: str) -> dict[str, Any]:
    info = get_faq_entitlement(tenant_id)
    if not info["faq_enabled"]:
        raise FaqEntitlementError(
            info["upgrade_message"] or "FAQ disabled",
            code="FAQ_DISABLED",
            payload=info,
        )
    if info["at_limit"]:
        raise FaqEntitlementError(
            info["upgrade_message"] or "FAQ quota reached",
            code="FAQ_QUOTA_EXCEEDED",
            payload=info,
        )
    return info
