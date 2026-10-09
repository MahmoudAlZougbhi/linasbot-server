"""Assert WhatsApp entitlement before Cloud connect / AI replies."""

from __future__ import annotations

from services.billing.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.billing.membership.feature_entitlements import whatsapp_allowed_for_plan


class WhatsAppPlanDenied(PermissionError):
    code = "WHATSAPP_PLAN_DENIED"


def assert_whatsapp_plan_allowed(tenant_id: str) -> None:
    """Fail closed for paid tenants without the WhatsApp plan flag.

    Subscription-exempt tenants (``SUBSCRIPTION_EXEMPT_TENANT_IDS`` env) skip the paid-plan check.
    Default exempt list is empty. Catalog features are SoT; stored entitlement.features may be stale.
    """

    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    plan_id = (ent.plan_id or "").strip().lower()
    status_ok = ent.status in {"active", "trial", "grace"} and plan_id not in {"", "none"}
    if status_ok and whatsapp_allowed_for_plan(plan_id):
        return
    from services.platform.feature_flags import flag_enabled

    if flag_enabled("period_balances"):
        from services.billing.membership.balances import purchased_remaining

        if purchased_remaining(tenant_id) > 0:
            return
    raise WhatsAppPlanDenied(f"WhatsApp requires an active paid plan (plan={ent.plan_id}, status={ent.status}).")
