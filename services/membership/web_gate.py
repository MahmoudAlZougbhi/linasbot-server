"""Assert Web Chat entitlement before widget connect / AI replies."""

from __future__ import annotations

from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.membership.feature_entitlements import web_allowed_for_plan


class WebPlanDenied(PermissionError):
    code = "WEB_PLAN_DENIED"


def assert_web_plan_allowed(tenant_id: str) -> None:
    """Fail closed for paid tenants without the Web Chat plan flag.

    Subscription-exempt tenants (default: ``linas``) are allowed.
    Catalog features are SoT; stored entitlement.features may be stale.
    """

    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    plan_id = (ent.plan_id or "").strip().lower()
    if ent.status not in {"active", "trial", "grace"} or plan_id in {"", "none"}:
        raise WebPlanDenied(f"Web Chat requires an active paid plan (plan={ent.plan_id}, status={ent.status}).")
    if not web_allowed_for_plan(plan_id):
        raise WebPlanDenied(f"Web Chat is not included on plan={ent.plan_id}. Upgrade required.")
