"""TikTok Enhanced Video Context connect API."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Request
from fastapi.responses import JSONResponse

from db.session import WhatsAppDatabaseUnavailable
from modules.core import app
from modules.tiktok_business_api import _actor, _error, _require_manager
from services.tiktok_business.ads_oauth import start_tiktok_ads_oauth
from services.tiktok_business.errors import TikTokBusinessError


@app.post("/api/tiktok/enhanced/connect/start")
async def tiktok_enhanced_connect_start(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = _require_manager(request)
    surface = str(body.get("return_surface") or "mobile").strip().lower()
    try:
        return start_tiktok_ads_oauth(
            tenant_id=session.tenant_id, actor_user_id=_actor(session), return_surface=surface
        )
    except TikTokBusinessError as exc:
        return _error(exc)
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "TIKTOK_DB_UNAVAILABLE"})
