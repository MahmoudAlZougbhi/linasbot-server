"""Assert comment_automation entitlement before Meta comment AI replies."""

from __future__ import annotations

from services.billing.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.billing.membership.feature_entitlements import comments_allowed_for_plan


class CommentAutomationDenied(PermissionError):
    code = "COMMENT_AUTOMATION_DENIED"


def assert_comment_automation_allowed(tenant_id: str) -> None:
    """Fail closed for paid tenants without comment_automation.

    Subscription-exempt tenants (``SUBSCRIPTION_EXEMPT_TENANT_IDS``) are allowed.
    Catalog features are SoT; stored entitlement.features may be stale.
    """

    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    plan_id = (ent.plan_id or "").strip().lower()
    status_ok = ent.status in {"active", "trial", "grace"} and plan_id not in {"", "none"}
    if status_ok and comments_allowed_for_plan(plan_id):
        return
    from services.platform.feature_flags import flag_enabled

    if flag_enabled("period_balances"):
        from services.billing.membership.balances import purchased_remaining

        if purchased_remaining(tenant_id) > 0:
            return
    raise CommentAutomationDenied(
        f"Comment automation requires an active paid plan (plan={ent.plan_id}, status={ent.status})."
    )
