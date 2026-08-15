"""Assert Web Chat entitlement before widget connect / AI replies."""

from __future__ import annotations

from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.plan_economics import PLAN_FEATURES


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
    features = PLAN_FEATURES.get(plan_id) or ent.features or {}
    if not features.get("web"):
        raise WebPlanDenied(f"Web Chat is not included on plan={ent.plan_id}. Upgrade required.")
