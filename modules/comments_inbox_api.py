"""Live Chat comments inbox: post grid and AI reply threads."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission
from modules.core import app
from services.access_channels import session_can_use_channel
from services.comments_inbox.media_feed import list_comment_media
from services.comments_inbox.threads import list_comment_threads
from services.comments_inbox.watchlist import PLATFORMS


def _platform(raw: str) -> str | None:
    plat = str(raw or "").strip().lower()
    return plat if plat in PLATFORMS else None


@app.get("/api/comments/media")
async def comments_media_grid(
    request: Request,
    platform: str = Query(default="instagram"),
    after: str = "",
    limit: int = Query(default=24, ge=1, le=50),
) -> Any:
    session = require_permission(request, "comments")
    plat = _platform(platform)
    if plat is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "unknown_platform"})
    if not session_can_use_channel(session, plat):
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await list_comment_media(tenant_id=session.tenant_id, platform=plat, after=after, limit=limit)
    return {"success": True, **result}


@app.get("/api/comments/media/{post_id}/threads")
async def comments_media_threads(
    request: Request,
    post_id: str,
    platform: str = Query(default="instagram"),
    limit: int = Query(default=50, ge=1, le=100),
) -> Any:
    session = require_permission(request, "comments")
    plat = _platform(platform)
    if plat is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "unknown_platform"})
    if not session_can_use_channel(session, plat):
        raise HTTPException(status_code=403, detail="Forbidden")
    result = await list_comment_threads(
        tenant_id=session.tenant_id,
        platform=plat,
        post_id=post_id,
        limit=limit,
    )
    return {"success": True, **result}
