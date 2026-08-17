"""Platform owner control center API."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.dashboard_session_service import session_service
from services.job_queue import job_queue
from services.owner_portal_service import analytics, list_subscribers
from services.platform_owner_service import platform_owner_service
from services.providers.router import provider_router
from services.tenant_custom_roles import tenant_custom_roles
from services.user_service import user_service


class SuspendBody(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=3, max_length=500)


class PlatformUserUpdateBody(BaseModel):
    status: str | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=12, max_length=128)


@app.get("/api/platform/metrics")
async def platform_metrics(request: Request) -> Any:
    require_platform_owner(request)
    return {
        "success": True,
        "business": platform_owner_service.business_metrics(),
        "queues": job_queue.depth(),
        "queue_backend": job_queue.backend,
        "queue_production_ready": job_queue.production_ready,
        "providers": provider_router.public_routes(),
    }


@app.get("/api/platform/analytics")
async def platform_analytics(
    request: Request,
    range_key: str = Query(default="last_7_days"),
) -> Any:
    require_platform_owner(request)
    try:
        return {"success": True, "analytics": analytics(range_key)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/platform/users")
async def platform_users(request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "subscribers": list_subscribers()}


@app.patch("/api/platform/users/{user_id}")
async def platform_update_user(user_id: str, body: PlatformUserUpdateBody, request: Request) -> Any:
    session = require_platform_owner(request)
    target = user_service.get_user_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if str(target.get("role") or "").lower() == "platform_owner":
        raise HTTPException(status_code=403, detail="Platform-owner accounts are CLI-managed")
    updates: dict[str, Any] = {}
    if body.status is not None:
        status = body.status.strip().lower()
        if status not in {"active", "blocked"}:
            raise HTTPException(status_code=400, detail="Status must be active or blocked")
        updates["status"] = status
    if body.role is not None:
        tenant_id = str(target.get("tenantId") or "").strip()
        updates["role"] = body.role
        updates["_custom_role_ids"] = tenant_custom_roles.role_ids(tenant_id)
    if body.password is not None:
        updates["password"] = body.password
    if not updates:
        raise HTTPException(status_code=400, detail="No supported changes supplied")
    try:
        user = user_service.update_user(user_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    session_service.revoke_all_for_user(user_id)
    platform_owner_service.log_action(
        actor_user_id=session.user_id,
        action="update_user",
        tenant_id=str(target.get("tenantId") or ""),
        details={"user_id": user_id, "fields": sorted(k for k in updates if not k.startswith("_"))},
    )
    return {"success": True, "user": user}


@app.get("/api/platform/tenants/{tenant_id}")
async def platform_tenant_detail(tenant_id: str, request: Request) -> Any:
    require_platform_owner(request)
    return {"success": True, "tenant": platform_owner_service.tenant_detail(tenant_id)}


@app.post("/api/platform/tenants/suspend")
async def platform_suspend(body: SuspendBody, request: Request) -> Any:
    session = require_platform_owner(request)
    platform_owner_service.suspend_tenant(
        actor_user_id=session.user_id,
        tenant_id=body.tenant_id,
        reason=body.reason,
    )
    return {"success": True}


@app.post("/api/platform/tenants/reactivate")
async def platform_reactivate(body: SuspendBody, request: Request) -> Any:
    session = require_platform_owner(request)
    platform_owner_service.reactivate_tenant(actor_user_id=session.user_id, tenant_id=body.tenant_id)
    return {"success": True}


@app.get("/api/platform/health-ops")
async def platform_health_ops(request: Request) -> Any:
    require_platform_owner(request)
    return {
        "success": True,
        "queues": job_queue.depth(),
        "notes": (
            "Durable Redis workers activate when REDIS_URL + LINAS_REQUIRE_REDIS=true. "
            "See docs/PHASE2_PRE_RELEASE_REPORT.md."
        ),
    }
