"""Platform-admin catalog, cost, and daily-edit HTTP facade. Tenant owners are not authorized."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.owner_portal.activation import activation_readiness
from services.owner_portal.catalog import (
    CatalogPublishBlocked,
    daily_edits_for_tenant,
    get_message_catalog,
    publish_message_catalog,
    save_message_catalog_draft,
    set_daily_edit_policy,
)
from services.owner_portal.costs import (
    credit_conversion_dry_run,
    message_ledger,
)
from services.owner_portal.costs import (
    platform_costs as load_platform_costs,
)
from services.owner_portal.costs import (
    tenant_costs as load_tenant_costs,
)
from services.owner_portal.messages import list_platform_message_flows, platform_message_flow


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
    return {"success": True, "catalog": get_message_catalog()}


@app.patch("/api/platform/message-catalog")
async def platform_message_catalog_draft(body: CatalogDraftBody, request: Request) -> Any:
    session = require_platform_owner(request)
    changes: dict[str, Any] = {}
    if body.ai_setup_daily_edit_limit is not None:
        changes["ai_setup_daily_edit_limit"] = body.ai_setup_daily_edit_limit
    if body.free is not None:
        changes["free"] = body.free
    if body.plans is not None:
        changes["plans"] = body.plans
    if body.topup_packs is not None:
        changes["topup_packs"] = body.topup_packs
    try:
        catalog = save_message_catalog_draft(
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
        catalog = publish_message_catalog(actor=session.user_id or session.email or "platform")
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
    return {
        "success": True,
        "dashboard": load_platform_costs(
            environment=environment,
            category=category,
            feature=feature,
            provider=provider,
            model=model,
            since=since,
            until=until,
            period=period,
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
    return {
        "success": True,
        "dashboard": load_tenant_costs(
            tenant_id,
            environment=environment,
            category=category,
            feature=feature,
            provider=provider,
            model=model,
            since=since,
            until=until,
            period=period,
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
    return {"success": True, "daily_edits": daily_edits_for_tenant(tid)}


@app.patch("/api/platform/daily-edits")
async def platform_daily_edits_policy(body: DailyEditPolicyBody, request: Request) -> Any:
    require_platform_owner(request)
    result = set_daily_edit_policy(tenant_id=body.tenant_id, limit=body.limit)
    if body.tenant_id:
        return {"success": True, "daily_edits": result}
    return {"success": True, **result}


@app.get("/api/platform/credit-conversion/dry-run")
async def platform_credit_conversion_dry_run(request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "dry_run": credit_conversion_dry_run()}


@app.get("/api/platform/activation-readiness")
async def platform_activation_readiness(request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "readiness": activation_readiness()}


@app.get("/api/platform/message-ledger/{tenant_id}")
async def platform_message_ledger(tenant_id: str, request: Request) -> Any:
    require_platform_owner(request)
    try:
        payload = message_ledger(tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, **payload}


@app.get("/api/platform/message-flows")
async def platform_message_flows(
    request: Request,
    tenant_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> Any:
    require_platform_owner(request)
    return {
        "success": True,
        "messages": list_platform_message_flows(tenant_id=tenant_id or "", limit=limit),
    }


@app.get("/api/platform/message-flows/{tenant_id}/{operation_id}")
async def platform_message_flow_detail(tenant_id: str, operation_id: str, request: Request) -> Any:
    require_platform_owner(request)
    detail = platform_message_flow(tenant_id=tenant_id, operation_id=operation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="message_flow_not_found")
    return {"success": True, "message": detail}
