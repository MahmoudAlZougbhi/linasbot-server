"""Authenticated WhatsApp Cloud connection + Embedded Signup APIs."""

from __future__ import annotations

from typing import Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.api_security import is_platform_owner, require_permission, require_session, user_has_permission
from modules.core import app
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags, whatsapp_config_key_presence
from services.whatsapp_cloud.embedded_signup import WhatsAppSignupError, complete_embedded_signup, start_embedded_signup
from services.whatsapp_cloud.entitlement import (
    WhatsAppEntitlementError,
    assert_whatsapp_connection_allowed,
    tenant_connection_status_payload,
)
from services.whatsapp_cloud.repository import WhatsAppCloudRepository


def _actor_id(session: Any) -> str:
    return str(session.user_id or session.email or "unknown")


def _require_wa_manager(request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    if not user_has_permission(session, "contentPublish") and not is_platform_owner(session):
        # Owners/admins with contentManagers may manage; require contentPublish for connect/disconnect.
        role = (session.role or "").strip().lower()
        if role not in {"owner", "admin", "platform_owner"}:
            raise HTTPException(status_code=403, detail="owner_or_admin_required")
    return session


@app.get("/api/whatsapp/cloud/status")
async def whatsapp_cloud_status(request: Request) -> Any:
    session = require_session(request)
    flags = get_whatsapp_cloud_flags()
    try:
        with whatsapp_session() as db:
            repo = WhatsAppCloudRepository(db)
            pilot = repo.get_active_pilot(session.tenant_id) is not None
            try:
                assert_whatsapp_connection_allowed(db, session.tenant_id)
                connectable = True
                blocker = None
            except WhatsAppEntitlementError as exc:
                connectable = False
                blocker = exc.code
            connections = [
                tenant_connection_status_payload(db, c, tenant_id=session.tenant_id)
                for c in repo.list_tenant_connections(session.tenant_id)
                if c.lifecycle_status != "revoked"
            ]
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "error": "WHATSAPP_DB_UNAVAILABLE",
                "message": "WhatsApp Cloud database is not configured",
                "config_keys_present": whatsapp_config_key_presence(),
            },
        )
    primary = connections[0] if connections else None
    lifecycle = primary["lifecycle_status"] if primary else "disconnected"
    ui_open = bool(flags.connection_ui_enabled or flags.public_availability)
    # Honest Phase 1: non-entitled tenants see Meta-approval wait, not a fake Coming Soon product.
    awaiting_meta = (not flags.public_availability) and (
        blocker
        in {
            "WHATSAPP_PILOT_REQUIRED",
            "WHATSAPP_ROLLOUT_DISABLED",
        }
    )
    return {
        "success": True,
        "platform": "whatsapp",
        "lifecycle_status": lifecycle,
        "connectable": bool(connectable and ui_open),
        "coming_soon": False,
        "awaiting_meta_approval": awaiting_meta and not (primary and lifecycle == "connected"),
        "public_availability": flags.public_availability,
        "pilot_entitled": pilot,
        "blocker_code": blocker,
        "blocker_message": (
            "WhatsApp integration awaits Meta App Review approval. "
            "Internal pilot accounts can connect now; public connect opens after Meta approval "
            "via the central WHATSAPP_CLOUD_PUBLIC_AVAILABILITY switch."
            if awaiting_meta
            else None
        ),
        "coexistence_feature": "whatsapp_business_app_onboarding",
        "connection": primary,
        "connections": connections,
        "flags": {
            "connection_ui_enabled": flags.connection_ui_enabled,
            "ai_replies_enabled": flags.ai_replies_enabled,
            "outbound_sends_enabled": flags.outbound_sends_enabled,
            "history_sync_enabled": flags.history_sync_enabled,
            "public_availability": flags.public_availability,
            "require_pilot_entitlement": flags.require_pilot_entitlement,
            "embedded_signup_config_configured": flags.embedded_signup_config_id_configured,
        },
    }


@app.post("/api/whatsapp/cloud/connect/start")
async def whatsapp_cloud_connect_start(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = _require_wa_manager(request)
    return_surface = str(body.get("return_surface") or "mobile").strip().lower()
    if return_surface not in {"mobile", "web", "bridge"}:
        return_surface = "mobile"
    try:
        result = start_embedded_signup(
            tenant_id=session.tenant_id,
            actor_user_id=_actor_id(session),
            return_surface=return_surface,
        )
        return result
    except WhatsAppEntitlementError as exc:
        return JSONResponse(status_code=403, content={"success": False, "error": exc.code, "message": exc.message})
    except WhatsAppSignupError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"success": False, "error": exc.code, "message": exc.message}
        )
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE"})


@app.get("/oauth/whatsapp/callback")
async def whatsapp_oauth_callback(request: Request) -> Any:
    """Meta / bridge completion callback — never lands on Operator Login."""

    params = request.query_params
    state = params.get("state") or ""
    code = params.get("code")
    error = params.get("error")
    error_reason = params.get("error_reason") or params.get("error_description")
    waba_id = params.get("waba_id") or params.get("wa_waba_id")
    phone_number_id = params.get("phone_number_id") or params.get("wa_phone_number_id")
    session_event = params.get("session_event")
    session_type = params.get("session_type")
    session_version = params.get("session_version")
    business_id = params.get("business_id")
    try:
        result = await complete_embedded_signup(
            state=state,
            code=code,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            error=error,
            error_reason=error_reason,
            session_event=session_event,
            session_type=session_type,
            session_version=session_version,
            business_id=business_id,
        )
        redirect = str(result.get("redirect_url") or "linasai://integrations?wa_connection=failed")
        return RedirectResponse(url=redirect, status_code=303)
    except WhatsAppSignupError as exc:
        # Safe public fallback — never Operator Login.
        html = (
            "<!doctype html><html><head><meta charset='utf-8'>"
            "<meta name='robots' content='noindex,nofollow'>"
            "<title>Return to Linas AI</title></head><body>"
            "<h1>You can return to Linas AI</h1>"
            "<p>WhatsApp connection did not complete. Open the Linas AI app and try again from Integrations.</p>"
            f"<p>Reference: {exc.code}</p>"
            "</body></html>"
        )
        return HTMLResponse(content=html, status_code=400, headers={"X-Robots-Tag": "noindex, nofollow"})


@app.post("/api/whatsapp/cloud/connect/complete")
async def whatsapp_cloud_connect_complete(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    """Authenticated completion for bridge page posting code + session assets."""

    # Bridge may call this without session when using state-bound one-time nonce only.
    state = str(body.get("state") or "")
    try:
        result = await complete_embedded_signup(
            state=state,
            code=body.get("code"),
            waba_id=body.get("waba_id"),
            phone_number_id=body.get("phone_number_id"),
            error=body.get("error"),
            error_reason=body.get("error_reason"),
            session_event=body.get("session_event"),
            session_type=body.get("session_type"),
            session_version=body.get("session_version"),
            business_id=body.get("business_id"),
        )
        return result
    except WhatsAppSignupError as exc:
        return JSONResponse(
            status_code=exc.http_status, content={"success": False, "error": exc.code, "message": exc.message}
        )


@app.get("/integrations/whatsapp/embedded-signup")
async def whatsapp_embedded_signup_bridge(request: Request) -> HTMLResponse:
    """Purpose-built noindex bridge for Meta Embedded Signup v4 coexistence."""

    from services.whatsapp_cloud.embedded_signup_bridge import render_embedded_signup_bridge_html

    flags = get_whatsapp_cloud_flags()
    html = render_embedded_signup_bridge_html(
        app_id=str(request.query_params.get("app_id") or flags.meta_app_id),
        state=str(request.query_params.get("state") or ""),
        config_id=str(request.query_params.get("config_id") or ""),
        redirect_uri=flags.oauth_redirect_uri,
    )
    return HTMLResponse(content=html, headers={"X-Robots-Tag": "noindex, nofollow"})
