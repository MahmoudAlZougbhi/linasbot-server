"""TikTok Enhanced Video Context connect / disconnect / refresh APIs."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Request
from fastapi.responses import JSONResponse

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.core import app
from modules.tiktok_business_api import _actor, _error, _require_manager
from services.tiktok_business.ads_config import tiktok_ads_redirect_uri
from services.tiktok_business.ads_oauth import disconnect_tiktok_enhanced, start_tiktok_ads_oauth
from services.tiktok_business.capability_probe import probe_enhanced_capabilities
from services.tiktok_business.errors import TikTokBusinessError
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.status import tiktok_integration_row


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


@app.post("/api/tiktok/enhanced/disconnect")
async def tiktok_enhanced_disconnect(request: Request) -> Any:
    session = _require_manager(request)
    try:
        await disconnect_tiktok_enhanced(tenant_id=session.tenant_id, actor_user_id=_actor(session))
    except TikTokBusinessError as exc:
        return _error(exc)
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "TIKTOK_DB_UNAVAILABLE"})
    return {"success": True, "platform": "tiktok", "integration": tiktok_integration_row(session.tenant_id)}


@app.post("/api/tiktok/enhanced/refresh")
async def tiktok_enhanced_refresh(request: Request) -> Any:
    session = _require_manager(request)
    try:
        with whatsapp_session() as db:
            repo = TikTokRepository(db)
            enhanced = TikTokEnhancedRepository(db)
            connection = repo.get_active_for_tenant(session.tenant_id)
            if connection is None:
                raise TikTokBusinessError(
                    "Connect TikTok first, then enable Enhanced Video Context.",
                    code="TIKTOK_CONNECT_REQUIRED",
                    http_status=409,
                )
            await probe_enhanced_capabilities(
                repo=enhanced,
                tenant_id=session.tenant_id,
                connection_id=connection.id,
                username=connection.username,
                display_name=connection.display_name,
                granted_scopes=list(connection.granted_scopes or []),
                force=False,
            )
            db.commit()
    except TikTokBusinessError as exc:
        return _error(exc)
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "TIKTOK_DB_UNAVAILABLE"})
    return {
        "success": True,
        "platform": "tiktok",
        "integration": tiktok_integration_row(session.tenant_id),
        "production_ads_redirect_uri": tiktok_ads_redirect_uri(),
    }
