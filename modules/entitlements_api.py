"""Subscription entitlements + store notification hooks."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner, require_session
from modules.core import app
from services.entitlements_service import (
    EntitlementStatus,
    apply_store_notification,
    entitlements_store,
    get_tenant_entitlement_public,
)
from services.plan_economics import PLAN_FAQ_MAX_ENTRIES, PLAN_FEATURES, PLAN_PRICES_USD, recommend_allowance


class StoreNotificationBody(BaseModel):
    tenant_id: str
    plan_id: Literal["lite", "starter", "growth", "pro", "max"]
    status: EntitlementStatus
    source: Literal["apple", "google"]
    original_transaction_id: str = Field(min_length=4)
    idempotency_key: str = Field(min_length=8)


@app.get("/api/entitlements/me")
async def get_my_entitlement(request: Request) -> Any:
    session = require_session(request)
    return {"success": True, "entitlement": get_tenant_entitlement_public(session.tenant_id)}


@app.get("/api/entitlements/plans")
async def list_plans() -> Any:
    """Authenticated mirror of the frozen five-plan catalog (same public fields)."""
    from services.membership.plan_catalog import CATALOG_VERSION, PLAN_CATALOG
    from services.plan_economics import PLAN_ADDITIONAL_SEATS

    plans = []
    for plan_id, price in PLAN_PRICES_USD.items():
        allowance = recommend_allowance(plan_id)
        features = PLAN_FEATURES[plan_id]
        plan = PLAN_CATALOG[plan_id]
        public_features = {
            k: v
            for k, v in features.items()
            if k
            in {
                "owner_assistant",
                "content_management",
                "customer_dm_automation",
                "faq_enabled",
                "comment_automation",
                "whatsapp",
                "web",
                "tiktok",
                "tenant_analytics",
                "instagram_dm",
                "facebook_dm",
            }
        }
        plans.append(
            {
                "plan_id": plan_id,
                "display_name": plan.display_name,
                "price_usd": price,
                "features": public_features,
                "faq_enabled": bool(features.get("faq_enabled")),
                "faq_max_entries": int(PLAN_FAQ_MAX_ENTRIES.get(plan_id, 0)),
                "faq_capacity": plan.faq_capacity,
                "included_credits": allowance.included_credits,
                "comment_automation": bool(features.get("comment_automation")),
                "whatsapp": bool(features.get("whatsapp")),
                "web": bool(features.get("web")),
                "tiktok": bool(features.get("tiktok")),
                "additional_seats": PLAN_ADDITIONAL_SEATS.get(plan_id),
                "additional_seats_unlimited": PLAN_ADDITIONAL_SEATS.get(plan_id) is None,
            }
        )
    return {
        "success": True,
        "catalog_version": CATALOG_VERSION,
        "billing_period": "monthly",
        "plans": plans,
    }


@app.post("/api/entitlements/store/notification")
async def store_notification(body: StoreNotificationBody, request: Request) -> Any:
    """Server-to-server style hook. Requires platform_owner until store webhook secrets land."""
    require_platform_owner(request)
    result = apply_store_notification(
        tenant_id=body.tenant_id,
        plan_id=body.plan_id,
        status=body.status,
        source=body.source,
        original_transaction_id=body.original_transaction_id,
        idempotency_key=body.idempotency_key,
    )
    return {"success": True, **result}


@app.post("/api/entitlements/admin/set-plan")
async def admin_set_plan(body: StoreNotificationBody, request: Request) -> Any:
    require_platform_owner(request)
    ent = entitlements_store.set_plan(
        tenant_id=body.tenant_id,
        plan_id=body.plan_id,
        status=body.status,
        source="admin",
        store_original_transaction_id=body.original_transaction_id,
    )
    return {"success": True, "entitlement": get_tenant_entitlement_public(ent.tenant_id)}
