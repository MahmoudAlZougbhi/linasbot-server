"""TikTok plan entitlement. Growth/Pro/Max only; linas exempt like WhatsApp."""

from __future__ import annotations

from services.billing.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.billing.membership.feature_entitlements import tiktok_allowed_for_plan
from services.integrations.tiktok.errors import TikTokPlanDeniedError


def assert_tiktok_plan_allowed(tenant_id: str) -> None:
    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"} or ent.plan_id in {"", "none"}:
        raise TikTokPlanDeniedError(f"TikTok requires an active paid plan (plan={ent.plan_id}, status={ent.status}).")
    if not tiktok_allowed_for_plan(ent.plan_id):
        raise TikTokPlanDeniedError(f"TikTok is not included on plan={ent.plan_id}. Upgrade required.")
