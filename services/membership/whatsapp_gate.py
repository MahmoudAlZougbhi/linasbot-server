"""Assert WhatsApp entitlement before Cloud connect / AI replies."""

from __future__ import annotations

from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.membership.feature_entitlements import whatsapp_allowed_for_plan


class WhatsAppPlanDenied(PermissionError):
    code = "WHATSAPP_PLAN_DENIED"


def assert_whatsapp_plan_allowed(tenant_id: str) -> None:
    """Fail closed for paid tenants without the WhatsApp plan flag.

    Subscription-exempt tenants (default: ``linas``) are allowed — they are not
    on the public paid matrix and must keep founder clinic WhatsApp workable.
    Catalog features are SoT; stored entitlement.features may be stale.
    """

    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"} or ent.plan_id in {"", "none"}:
        raise WhatsAppPlanDenied(f"WhatsApp requires an active paid plan (plan={ent.plan_id}, status={ent.status}).")
    if not whatsapp_allowed_for_plan(ent.plan_id):
        raise WhatsAppPlanDenied(f"WhatsApp is not included on plan={ent.plan_id}. Upgrade required.")
