"""Authenticated WhatsApp Cloud connection + conversation control APIs."""

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
    connection_status_payload,
)
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, create_message_template, list_message_templates
from services.whatsapp_cloud.repository import WhatsAppCloudRepository, conversation_public_view


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
                connection_status_payload(db, c)
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
    return {
        "success": True,
        "platform": "whatsapp",
        "lifecycle_status": lifecycle,
        "connectable": connectable and flags.connection_ui_enabled,
        "coming_soon": not flags.connection_ui_enabled,
        "public_availability": flags.public_availability,
        "pilot_entitled": pilot,
        "blocker_code": blocker,
        "coexistence_feature": "whatsapp_business_app_onboarding",
        "connection": primary,
        "connections": connections,
        "flags": {
            "connection_ui_enabled": flags.connection_ui_enabled,
            "ai_replies_enabled": flags.ai_replies_enabled,
            "outbound_sends_enabled": flags.outbound_sends_enabled,
            "history_sync_enabled": flags.history_sync_enabled,
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
        return JSONResponse(status_code=exc.http_status, content={"success": False, "error": exc.code, "message": exc.message})
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
    try:
        result = await complete_embedded_signup(
            state=state,
            code=code,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            error=error,
            error_reason=error_reason,
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
        )
        return result
    except WhatsAppSignupError as exc:
        return JSONResponse(status_code=exc.http_status, content={"success": False, "error": exc.code, "message": exc.message})


@app.get("/integrations/whatsapp/embedded-signup")
async def whatsapp_embedded_signup_bridge(request: Request) -> HTMLResponse:
    """Purpose-built noindex bridge for Meta Embedded Signup v4 coexistence."""

    flags = get_whatsapp_cloud_flags()
    state = request.query_params.get("state") or ""
    config_id = request.query_params.get("config_id") or ""
    app_id = request.query_params.get("app_id") or flags.meta_app_id
    feature = "whatsapp_business_app_onboarding"
    redirect_uri = flags.oauth_redirect_uri
    # Use replace tokens so JavaScript braces do not conflict with Python formatting.
    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="robots" content="noindex,nofollow"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Connect WhatsApp — Linas AI</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 2rem; background: #0b1220; color: #f5f7fb; }
    .card { max-width: 28rem; margin: 0 auto; }
    button { background: #25D366; color: #04210f; border: 0; padding: .85rem 1.2rem; border-radius: 10px; font-weight: 700; width: 100%; }
    p { opacity: .85; line-height: 1.45; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Connect WhatsApp</h1>
    <p>Continue to Meta to link your existing WhatsApp Business app number (coexistence). You will return to Linas AI.</p>
    <button id="start" type="button">Continue with Meta</button>
    <p id="status"></p>
  </div>
  <script>
    window.fbAsyncInit = function() {
      FB.init({ appId: __APP_ID__, autoLogAppEvents: true, xfbml: true, version: 'v24.0' });
    };
    (function(d, s, id){
      var js, fjs = d.getElementsByTagName(s)[0];
      if (d.getElementById(id)) return;
      js = d.createElement(s); js.id = id;
      js.src = "https://connect.facebook.net/en_US/sdk.js";
      fjs.parentNode.insertBefore(js, fjs);
    }(document, 'script', 'facebook-jssdk'));

    const state = __STATE__;
    const configId = __CONFIG_ID__;
    const featureType = __FEATURE__;
    const redirectUri = __REDIRECT__;
    const statusEl = document.getElementById('status');

    function finish(payload) {
      const q = new URLSearchParams(Object.assign({ state: state }, payload));
      window.location = redirectUri + (redirectUri.includes('?') ? '&' : '?') + q.toString();
    }

    document.getElementById('start').addEventListener('click', function() {
      statusEl.textContent = 'Opening Meta…';
      if (!window.FB) { statusEl.textContent = 'Meta SDK failed to load.'; return; }
      FB.login(function(response) {
        if (!response || response.error) {
          finish({ error: 'login_failed' });
          return;
        }
        const auth = response.authResponse || {};
        const code = auth.code || '';
        finish({
          code: code,
          waba_id: (window.__WA_WABA_ID || ''),
          phone_number_id: (window.__WA_PHONE_NUMBER_ID || '')
        });
      }, {
        config_id: configId,
        response_type: 'code',
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: featureType,
          sessionInfoVersion: '3'
        }
      });
    });

    window.addEventListener('message', function(event) {
      if (!event.origin.includes('facebook.com') && !event.origin.includes('fb.com')) return;
      try {
        const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
        if (!data) return;
        if (data.type === 'WA_EMBEDDED_SIGNUP' || data.event === 'FINISH' || data.waba_id) {
          window.__WA_WABA_ID = data.waba_id || (data.data && data.data.waba_id) || '';
          window.__WA_PHONE_NUMBER_ID = data.phone_number_id || (data.data && data.data.phone_number_id) || '';
        }
      } catch (e) {}
    });
  </script>
</body>
</html>"""
    import json as _json
    html = (
        html.replace("__APP_ID__", _json.dumps(str(app_id)))
        .replace("__STATE__", _json.dumps(str(state)))
        .replace("__CONFIG_ID__", _json.dumps(str(config_id)))
        .replace("__FEATURE__", _json.dumps(str(feature)))
        .replace("__REDIRECT__", _json.dumps(str(redirect_uri)))
    )
    return HTMLResponse(content=html, headers={"X-Robots-Tag": "noindex, nofollow"})


@app.post("/api/whatsapp/cloud/connections/{connection_id}/ai/enable")
async def whatsapp_enable_ai(connection_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        conn.ai_default_enabled = True
        repo.add_audit(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            actor_user_id=_actor_id(session),
            event_type="ai_default_enabled",
            detail={},
        )
        return {"success": True, "connection": connection_status_payload(db, conn)}


@app.post("/api/whatsapp/cloud/connections/{connection_id}/ai/disable")
async def whatsapp_disable_ai(connection_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        conn.ai_default_enabled = False
        repo.add_audit(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            actor_user_id=_actor_id(session),
            event_type="ai_default_disabled",
            detail={},
        )
        return {"success": True, "connection": connection_status_payload(db, conn)}


@app.post("/api/whatsapp/cloud/conversations/{conversation_id}/pause")
async def whatsapp_pause_conversation(conversation_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conv = repo.get_tenant_conversation(tenant_id=session.tenant_id, conversation_id=conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        repo.pause_conversation(conv, reason="operator_pause", actor_user_id=_actor_id(session))
        return {"success": True, "conversation": conversation_public_view(conv)}


@app.post("/api/whatsapp/cloud/conversations/{conversation_id}/resume")
async def whatsapp_resume_conversation(conversation_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conv = repo.get_tenant_conversation(tenant_id=session.tenant_id, conversation_id=conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        repo.resume_conversation(conv, actor_user_id=_actor_id(session))
        return {"success": True, "conversation": conversation_public_view(conv)}


@app.post("/api/whatsapp/cloud/connections/{connection_id}/disconnect")
async def whatsapp_disconnect(connection_id: str, request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = _require_wa_manager(request)
    role = (session.role or "").strip().lower()
    if role not in {"owner", "platform_owner"}:
        raise HTTPException(status_code=403, detail="owner_only_disconnect")
    confirm = str(body.get("confirm") or "").strip().upper()
    if confirm != "DISCONNECT":
        raise HTTPException(status_code=400, detail="confirm_DISCONNECT_required")
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        repo.revoke_connection(conn, actor_user_id=_actor_id(session), reason="owner_disconnect")
        repo.add_audit(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            actor_user_id=_actor_id(session),
            event_type="connection_revoked",
            detail={"reason": "owner_disconnect"},
        )
        return {"success": True, "lifecycle_status": "revoked"}


@app.get("/api/whatsapp/cloud/connections/{connection_id}/templates")
async def whatsapp_list_templates(connection_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        token = repo.load_access_token(conn)
    try:
        templates = await list_message_templates(access_token=token, waba_id=conn.waba_id)
    except WhatsAppGraphError as exc:
        return JSONResponse(status_code=502, content={"success": False, "error": exc.code, "message": exc.message})
    # Redact nothing sensitive — templates are public metadata.
    safe = [
        {
            "id": t.get("id"),
            "name": t.get("name"),
            "status": t.get("status"),
            "language": t.get("language"),
            "category": t.get("category"),
        }
        for t in templates
    ]
    return {"success": True, "templates": safe}


@app.post("/api/whatsapp/cloud/connections/{connection_id}/templates")
async def whatsapp_create_template(connection_id: str, request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = _require_wa_manager(request)
    name = str(body.get("name") or "").strip()
    language = str(body.get("language") or "en_US").strip()
    category = str(body.get("category") or "UTILITY").strip().upper()
    body_text = str(body.get("body_text") or "").strip()
    if not name or not body_text:
        raise HTTPException(status_code=400, detail="name_and_body_text_required")
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        token = repo.load_access_token(conn)
        waba_id = conn.waba_id
    try:
        created = await create_message_template(
            access_token=token,
            waba_id=waba_id,
            name=name,
            language=language,
            category=category,
            body_text=body_text,
        )
    except WhatsAppGraphError as exc:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": exc.code, "message": exc.message},
        )
    return {
        "success": True,
        "template": {
            "id": created.get("id"),
            "status": created.get("status"),
            "name": name,
            "language": language,
            "category": category,
        },
    }


@app.post("/api/whatsapp/cloud/pilot/grant")
async def whatsapp_pilot_grant(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    tenant_id = str(body.get("tenant_id") or "").strip().lower()
    reason = str(body.get("reason") or "").strip()
    if not tenant_id or not reason:
        raise HTTPException(status_code=400, detail="tenant_id_and_reason_required")
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        row = repo.grant_pilot(tenant_id=tenant_id, granted_by_user_id=_actor_id(session), reason=reason)
        repo.add_audit(
            tenant_id=tenant_id,
            actor_user_id=_actor_id(session),
            event_type="pilot_granted",
            detail={"reason": reason},
        )
        return {"success": True, "tenant_id": row.tenant_id, "status": row.status}


@app.post("/api/whatsapp/cloud/pilot/revoke")
async def whatsapp_pilot_revoke(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    tenant_id = str(body.get("tenant_id") or "").strip().lower()
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        row = repo.revoke_pilot(tenant_id=tenant_id, actor_user_id=_actor_id(session))
        if row is None:
            raise HTTPException(status_code=404, detail="pilot_not_found")
        return {"success": True, "tenant_id": row.tenant_id, "status": row.status}
