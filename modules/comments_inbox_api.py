"""Live Chat comments inbox: post grid, watchlist, and AI reply threads."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from modules.api_security import require_permission
from modules.core import app
from services.access_channels import session_can_use_channel
from services.comments_inbox.media_feed import list_comment_media
from services.comments_inbox.threads import list_comment_threads
from services.comments_inbox.watchlist import PLATFORMS, apply_watch_patch, platform_watch


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


@app.get("/api/comments/watchlist")
async def comments_watchlist_get(request: Request, platform: str = Query(default="instagram")) -> Any:
    session = require_permission(request, "comments")
    plat = _platform(platform)
    if plat is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "unknown_platform"})
    if not session_can_use_channel(session, plat):
        raise HTTPException(status_code=403, detail="Forbidden")
    return {"success": True, "platform": plat, "watch": platform_watch(session.tenant_id, plat)}


@app.patch("/api/comments/watchlist")
async def comments_watchlist_patch(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_permission(request, "commentsManage")
    plat = _platform(str(body.get("platform") or ""))
    if plat is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "unknown_platform"})
    if not session_can_use_channel(session, plat):
        raise HTTPException(status_code=403, detail="Forbidden")
    raw_ids = body.get("known_ids") or body.get("post_ids")
    known = [str(item) for item in raw_ids] if isinstance(raw_ids, list) else None
    selected = body.get("selected")
    watch = apply_watch_patch(
        session.tenant_id,
        platform=plat,
        mode=str(body.get("mode") or "") or None,
        post_id=str(body.get("post_id") or ""),
        selected=bool(selected) if isinstance(selected, bool) else None,
        known_ids=known,
        post_ids=[str(item) for item in body["post_ids"]]
        if isinstance(body.get("post_ids"), list) and "post_id" not in body
        else None,
    )
    return {"success": True, "platform": plat, "watch": watch}


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
