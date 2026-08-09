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
    plan_id: Literal["starter", "growth", "pro", "max"]
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
    plans = []
    for plan_id, price in PLAN_PRICES_USD.items():
        allowance = recommend_allowance(plan_id)
        plans.append(
            {
                "plan_id": plan_id,
                "price_usd": price,
                "features": PLAN_FEATURES[plan_id],
                "faq_enabled": bool(PLAN_FEATURES[plan_id].get("faq_enabled")),
                "faq_max_entries": int(PLAN_FAQ_MAX_ENTRIES.get(plan_id, 0)),
                "included_credits": allowance.included_credits,
                "included_dm_replies": allowance.included_dm_replies,
                "included_images": allowance.included_images,
                "included_videos": allowance.included_videos,
            }
        )
    return {"success": True, "plans": plans}


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
