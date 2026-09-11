"""Platform-admin catalog, cost, and daily-edit APIs. Tenant owners are not authorized."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.membership.catalog_admin import CatalogPublishBlocked, current_catalog, publish, update_draft
from services.membership.conversion_dry_run import dry_run_credit_inventory
from services.membership.cost_dashboard import global_dashboard, period_bounds, tenant_dashboard
from services.membership.daily_edits import decision_payload, set_platform_baseline, set_tenant_override, status


class CatalogDraftBody(BaseModel):
    ai_setup_daily_edit_limit: int | None = Field(default=None, ge=0, le=10_000)
    free: dict[str, Any] | None = None
    plans: dict[str, Any] | None = None
    topup_packs: dict[str, Any] | list[dict[str, Any]] | None = None
    reason: str = ""


class DailyEditPolicyBody(BaseModel):
    tenant_id: str | None = None
    limit: int = Field(ge=0, le=10_000)
    reason: str = ""


@app.get("/api/platform/message-catalog")
async def platform_message_catalog(request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "catalog": current_catalog()}


@app.patch("/api/platform/message-catalog")
async def platform_message_catalog_draft(body: CatalogDraftBody, request: Request) -> Any:
    session = require_platform_owner(request)
    changes: dict[str, Any] = {}
    if body.ai_setup_daily_edit_limit is not None:
        changes["ai_setup_daily_edit_limit"] = body.ai_setup_daily_edit_limit
        set_platform_baseline(body.ai_setup_daily_edit_limit)
    if body.free is not None:
        changes["free"] = body.free
    if body.plans is not None:
        changes["plans"] = body.plans
    if body.topup_packs is not None:
        changes["topup_packs"] = body.topup_packs
    try:
        catalog = update_draft(
            actor=session.user_id or session.email or "platform",
            changes=changes,
            reason=body.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "catalog": catalog}


@app.post("/api/platform/message-catalog/publish")
async def platform_message_catalog_publish(request: Request) -> Any:
    session = require_platform_owner(request)
    try:
        catalog = publish(actor=session.user_id or session.email or "platform")
    except CatalogPublishBlocked as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "free_offer_unconfigured", "unconfigured_fields": exc.fields},
        ) from exc
    return {"success": True, "catalog": catalog}


@app.get("/api/platform/costs")
async def platform_costs(
    request: Request,
    environment: str | None = Query(default=None),
    category: str | None = Query(default=None),
    feature: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    period: str | None = Query(default=None),
) -> Any:
    require_platform_owner(request)
    start, end = period_bounds(period)
    env = (environment or "").strip() or None
    return {
        "success": True,
        "dashboard": global_dashboard(
            environment=env,
            category=category,
            feature=feature,
            provider=provider,
            model=model,
            since=since or start,
            until=until or end,
        ),
    }


@app.get("/api/platform/costs/tenants/{tenant_id}")
async def platform_tenant_costs(
    tenant_id: str,
    request: Request,
    environment: str | None = Query(default=None),
    category: str | None = Query(default=None),
    feature: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    period: str | None = Query(default=None),
) -> Any:
    require_platform_owner(request)
    start, end = period_bounds(period)
    env = (environment or "").strip() or None
    return {
        "success": True,
        "dashboard": tenant_dashboard(
            tenant_id,
            environment=env,
            category=category,
            feature=feature,
            provider=provider,
            model=model,
            since=since or start,
            until=until or end,
        ),
    }


@app.get("/api/platform/daily-edits")
async def platform_daily_edits(
    request: Request,
    tenant_id: str = Query(default=""),
) -> Any:
    require_platform_owner(request)
    tid = tenant_id.strip()
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    return {"success": True, "daily_edits": decision_payload(status(tid))}


@app.patch("/api/platform/daily-edits")
async def platform_daily_edits_policy(body: DailyEditPolicyBody, request: Request) -> Any:
    require_platform_owner(request)
    if body.tenant_id:
        set_tenant_override(body.tenant_id, body.limit)
        return {"success": True, "daily_edits": decision_payload(status(body.tenant_id))}
    set_platform_baseline(body.limit)
    return {"success": True, "limit": body.limit, "source": "platform_baseline"}


@app.get("/api/platform/credit-conversion/dry-run")
async def platform_credit_conversion_dry_run(request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "dry_run": dry_run_credit_inventory()}


@app.get("/api/platform/activation-readiness")
async def platform_activation_readiness(request: Request) -> Any:
    require_platform_owner(request)
    from services.membership.activation_readiness import activation_readiness

    return {"success": True, "readiness": activation_readiness()}


@app.get("/api/platform/message-ledger/{tenant_id}")
async def platform_message_ledger(tenant_id: str, request: Request) -> Any:
    require_platform_owner(request)
    from services.membership.message_ledger import snapshot_dict
    from services.membership.reconcile import ledger_health

    tid = tenant_id.strip()
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    return {"success": True, "ledger": snapshot_dict(tid), "health": ledger_health(tid)}


@app.get("/api/platform/message-flows")
async def platform_message_flows(
    request: Request,
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> Any:
    require_platform_owner(request)
    from services.customer_ai.turn_inspector import list_message_flows

    return {
        "success": True,
        "messages": list_message_flows(tenant_id=(tenant_id or "").strip(), limit=limit),
    }


@app.get("/api/platform/message-flows/{tenant_id}/{operation_id}")
async def platform_message_flow_detail(tenant_id: str, operation_id: str, request: Request) -> Any:
    require_platform_owner(request)
    from services.customer_ai.turn_inspector import get_message_flow

    detail = get_message_flow(tenant_id=tenant_id, operation_id=operation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="message_flow_not_found")
    return {"success": True, "message": detail}
