"""Platform owner control center API."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from pydantic import BaseModel, Field

from modules.api_security import require_platform_owner
from modules.core import app
from services.job_queue import job_queue
from services.platform_owner_service import platform_owner_service
from services.providers.router import provider_router


class SuspendBody(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=3, max_length=500)


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
