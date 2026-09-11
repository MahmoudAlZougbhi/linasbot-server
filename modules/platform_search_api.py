"""Platform-admin search index controls. No unmetered bypass of processing budgets."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from modules.api_security import require_platform_owner
from modules.core import app
from services.customer_ai.search.force_reindex import force_reindex_tenant


@app.post("/api/platform/customer-ai-index/{tenant_id}/reindex")
async def platform_force_reindex(tenant_id: str, request: Request) -> Any:
    require_platform_owner(request)
    tid = tenant_id.strip()
    if not tid:
        raise HTTPException(status_code=400, detail="tenant_id is required")
    result = await force_reindex_tenant(tid)
    status = 200
    if result.get("reason") == "unpublished":
        status = 409
    elif result.get("reason") in {"PROCESSING_CONCURRENCY", "PROCESSING_DAILY_ATTEMPTS"}:
        status = 429
    if status != 200:
        raise HTTPException(status_code=status, detail=result)
    return {"success": True, "index": result}
