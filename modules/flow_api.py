"""
Activity Flow API - Serves User ↔ Bot ↔ AI interaction logs for dashboard transparency.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import HTTPException, Query, Request

from modules.api_security import is_platform_owner, require_session
from modules.core import app
from services.interaction_flow_logger import get_recent_flows


@app.get("/api/flow/logs")
async def get_flow_logs(
    request: Request,
    limit: int = 50,
    search: str | None = None,
    tenant_id: str | None = Query(default=None),
) -> Any:
    """
    Get recent interaction flow entries for the Activity Flow dashboard.
    Shows: User message → Bot → AI → Bot → User
    search: Filter by phone number (partial match)
    """
    session = require_session(request)
    session_tenant = session.tenant_id.strip().lower()
    requested_tenant = (tenant_id or session_tenant).strip().lower()
    if requested_tenant != session_tenant and not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="Cross-tenant logs are forbidden")
    # Run in thread pool so file read / JSON parse don't block the event loop.
    # Exact tenant filtering is mandatory; historical rows without tenant_id are excluded.
    logs = await asyncio.to_thread(
        get_recent_flows,
        limit=min(limit, 100),
        search_phone=search,
        tenant_id=requested_tenant,
    )
    return {"success": True, "data": logs, "count": len(logs)}
