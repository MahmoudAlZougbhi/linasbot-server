"""TikTok comments inbox + connected posts for the unified comments UI."""

from __future__ import annotations

from typing import Any

from fastapi import Query, Request
from fastapi.responses import JSONResponse

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.api_security import require_session
from modules.core import app
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.status import tiktok_integration_row


@app.get("/api/tiktok/comments")
async def tiktok_comments_inbox(request: Request, limit: int = Query(default=50, ge=1, le=100)) -> Any:
    session = require_session(request)
    try:
        with whatsapp_session() as db:
            repo = TikTokRepository(db)
            connection = repo.get_active_for_tenant(session.tenant_id)
            content = TikTokContentRepository(db)
            items = content.list_comments_inbox(
                tenant_id=session.tenant_id,
                limit=limit,
                connection_id=connection.id if connection else None,
            )
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "TIKTOK_DB_UNAVAILABLE"})
    row = tiktok_integration_row(session.tenant_id)
    status = "ok"
    if not row.get("connected"):
        status = "disconnected"
    elif row.get("connection_status") == "permission_required":
        status = "permission_pending"
    elif row.get("connection_status") == "error":
        status = "error"
    elif not items:
        status = "empty"
    return {
        "success": True,
        "platform": "tiktok",
        "status": status,
        "connection_status": row.get("connection_status"),
        "comments": items,
    }


@app.get("/api/comments/inbox")
async def unified_comments_inbox(
    request: Request,
    platform: str = Query(default="tiktok"),
    limit: int = Query(default=50, ge=1, le=100),
) -> Any:
    """Unified comments inbox. Meta filters are unchanged — this path serves TikTok stored comments."""

    require_session(request)
    plat = (platform or "").strip().lower()
    if plat in {"instagram", "facebook"}:
        return {
            "success": True,
            "platform": plat,
            "status": "meta_unchanged",
            "comments": [],
            "message": "Instagram and Facebook comment filters are unchanged; use existing Meta comment surfaces.",
        }
    if plat != "tiktok":
        return JSONResponse(status_code=404, content={"success": False, "error": "unknown_platform"})
    return await tiktok_comments_inbox(request, limit=limit)
