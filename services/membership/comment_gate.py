"""Assert comment_automation entitlement before Meta comment AI replies."""

from __future__ import annotations

from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.membership.feature_entitlements import comments_allowed_for_plan


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
    if not comments_allowed_for_plan(ent.plan_id):
        raise CommentAutomationDenied(f"Comment automation is not included on plan={ent.plan_id}. Upgrade required.")
