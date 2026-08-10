"""Assert comment_automation entitlement before Meta comment AI replies."""

from __future__ import annotations

from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.plan_economics import PLAN_FEATURES


class CommentAutomationDenied(PermissionError):
    code = "COMMENT_AUTOMATION_DENIED"


def assert_comment_automation_allowed(tenant_id: str) -> None:
    """Fail closed for paid tenants without comment_automation.

    Subscription-exempt tenants (default: ``linas``) are allowed — they are not
    on the public paid matrix and must keep founder clinic comments workable.
    Catalog features are SoT; stored entitlement.features may be stale.
    """

    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"} or ent.plan_id in {"", "none"}:
        raise CommentAutomationDenied(
            f"Comment automation requires an active paid plan (plan={ent.plan_id}, status={ent.status})."
        )
    features = PLAN_FEATURES.get(ent.plan_id) or ent.features or {}
    if not features.get("comment_automation"):
        raise CommentAutomationDenied(f"Comment automation is not included on plan={ent.plan_id}. Upgrade required.")
