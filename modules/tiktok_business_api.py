"""TikTok Business connect / disconnect / status APIs."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from db.session import WhatsAppDatabaseUnavailable
from modules.api_security import is_platform_owner, require_permission, require_session, user_has_permission
from modules.core import app
from services.tiktok_business.config import tiktok_config_key_presence, tiktok_redirect_uri, tiktok_webhook_callback_url
from services.tiktok_business.errors import TikTokBusinessError
from services.tiktok_business.oauth import disconnect_tiktok, start_tiktok_oauth
from services.tiktok_business.status import tiktok_integration_row


def _actor(session: Any) -> str:
    return str(session.user_id or session.email or "unknown")


def _require_manager(request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    role = (session.role or "").strip().lower()
    if role not in {"owner", "admin", "platform_owner"} and not user_has_permission(session, "contentPublish"):
        if not is_platform_owner(session):
            raise HTTPException(status_code=403, detail="owner_or_admin_required")
    return session


def _error(exc: TikTokBusinessError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.http_status,
        content={"success": False, "error": exc.code, "message": exc.message},
    )


@app.get("/api/tiktok/status")
async def tiktok_status(request: Request) -> Any:
    session = require_session(request)
    row = tiktok_integration_row(session.tenant_id)
    return {
        "success": True,
        "platform": "tiktok",
        "integration": row,
        "production_redirect_uri": tiktok_redirect_uri(),
        "webhook_callback_url": tiktok_webhook_callback_url(),
        "config_keys_present": tiktok_config_key_presence(),
    }


@app.post("/api/tiktok/connect/start")
async def tiktok_connect_start(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = _require_manager(request)
    surface = str(body.get("return_surface") or "mobile").strip().lower()
    try:
        return start_tiktok_oauth(tenant_id=session.tenant_id, actor_user_id=_actor(session), return_surface=surface)
    except TikTokBusinessError as exc:
        return _error(exc)
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "TIKTOK_DB_UNAVAILABLE"})


@app.post("/api/tiktok/disconnect")
async def tiktok_disconnect(request: Request) -> Any:
    session = require_permission(request, "settings")
    try:
        await disconnect_tiktok(tenant_id=session.tenant_id, actor_user_id=_actor(session))
    except TikTokBusinessError as exc:
        return _error(exc)
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "TIKTOK_DB_UNAVAILABLE"})
    return {"success": True, "platform": "tiktok", "integration": tiktok_integration_row(session.tenant_id)}


@app.post("/api/tiktok/reconnect")
async def tiktok_reconnect(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    return await tiktok_connect_start(request, body)
