"""TikTok plan entitlement. Growth/Pro/Max only; linas exempt like WhatsApp."""

from __future__ import annotations

from services.entitlements_service import entitlements_store, is_subscription_exempt_tenant
from services.plan_economics import PLAN_FEATURES
from services.tiktok_business.errors import TikTokPlanDeniedError


def assert_tiktok_plan_allowed(tenant_id: str) -> None:
    if is_subscription_exempt_tenant(tenant_id):
        return
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"} or ent.plan_id in {"", "none"}:
        raise TikTokPlanDeniedError(
            f"TikTok requires an active paid plan (plan={ent.plan_id}, status={ent.status})."
        )
    features = PLAN_FEATURES.get(ent.plan_id) or ent.features or {}
    if not features.get("tiktok"):
        raise TikTokPlanDeniedError(f"TikTok is not included on plan={ent.plan_id}. Upgrade required.")
