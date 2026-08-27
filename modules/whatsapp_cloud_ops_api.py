"""WhatsApp Cloud ops APIs: test send, templates, conversations, pilot admin."""

from __future__ import annotations

import re
from typing import Any

from fastapi import Body, HTTPException, Request
from fastapi.responses import JSONResponse

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.api_security import is_platform_owner, require_permission, require_session, user_has_permission
from modules.core import app
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags, whatsapp_config_key_presence
from services.whatsapp_cloud.entitlement import connection_status_payload
from services.whatsapp_cloud.graph_client import (
    WhatsAppGraphError,
    create_message_template,
    list_message_templates,
    send_text_message,
)
from services.whatsapp_cloud.repository import WhatsAppCloudRepository, conversation_public_view

_SAFE_RECIPIENT_FORMAT_RE = re.compile(r"^[+\d\s()-]+$")
_INTERNATIONAL_RECIPIENT_RE = re.compile(r"^[1-9]\d{7,14}$")


def _normalize_whatsapp_recipient(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw or _SAFE_RECIPIENT_FORMAT_RE.fullmatch(raw) is None:
        return None
    if raw.count("+") > 1 or ("+" in raw and not raw.startswith("+")):
        return None
    digits = re.sub(r"[+\s()-]", "", raw)
    return digits if _INTERNATIONAL_RECIPIENT_RE.fullmatch(digits) is not None else None


def _actor_id(session: Any) -> str:
    return str(session.user_id or session.email or "unknown")


def _require_wa_manager(request: Request) -> Any:
    session = require_permission(request, "contentManagers")
    if not user_has_permission(session, "contentPublish") and not is_platform_owner(session):
        role = (session.role or "").strip().lower()
        if role not in {"owner", "admin", "platform_owner"}:
            raise HTTPException(status_code=403, detail="owner_or_admin_required")
    return session


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
        from services.whatsapp_cloud.smart_followup.hooks import cancel_tenant_followups

        cancel_tenant_followups(db, tenant_id=session.tenant_id, reason="ai_disabled")
        return {"success": True, "connection": connection_status_payload(db, conn)}


@app.get("/api/whatsapp/cloud/connections/{connection_id}/conversations")
async def whatsapp_list_conversations(connection_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        rows = repo.list_connection_conversations(tenant_id=session.tenant_id, connection_id=connection_id, limit=50)
        return {"success": True, "conversations": [conversation_public_view(c) for c in rows]}


@app.post("/api/whatsapp/cloud/conversations/{conversation_id}/pause")
async def whatsapp_pause_conversation(conversation_id: str, request: Request) -> Any:
    session = _require_wa_manager(request)
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conv = repo.get_tenant_conversation(tenant_id=session.tenant_id, conversation_id=conversation_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="conversation_not_found")
        repo.pause_conversation(conv, reason="operator_pause", actor_user_id=_actor_id(session))
        from services.whatsapp_cloud.smart_followup.hooks import cancel_conversation_followups

        cancel_conversation_followups(
            db,
            tenant_id=session.tenant_id,
            conversation_id=conv.id,
            reason="conversation_paused",
        )
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


@app.post("/api/whatsapp/cloud/connections/{connection_id}/test-message")
async def whatsapp_send_test_message(
    connection_id: str, request: Request, body: dict[str, Any] = Body(default={})
) -> Any:
    """Real Cloud API test send for App Review filming — never fakes success."""

    session = _require_wa_manager(request)
    flags = get_whatsapp_cloud_flags()
    if not flags.outbound_sends_enabled:
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": "WHATSAPP_OUTBOUND_DISABLED", "message": "Outbound sends are disabled"},
        )
    to_wa_id = _normalize_whatsapp_recipient(body.get("to_wa_id") or body.get("to"))
    text = str(body.get("text") or body.get("message") or "").strip()
    if to_wa_id is None:
        raise HTTPException(status_code=400, detail="to_wa_id_required")
    if not text or len(text) > 1000:
        raise HTTPException(status_code=400, detail="text_required_max_1000")
    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        conn = repo.get_tenant_connection(tenant_id=session.tenant_id, connection_id=connection_id)
        if conn is None:
            raise HTTPException(status_code=404, detail="connection_not_found")
        if conn.lifecycle_status != "connected":
            raise HTTPException(status_code=409, detail="connection_not_connected")
        token = repo.load_access_token(conn)
        phone_number_id = conn.phone_number_id
        repo.add_audit(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            actor_user_id=_actor_id(session),
            event_type="test_message_requested",
            detail={"to_wa_id_len": len(to_wa_id), "text_len": len(text)},
        )
    try:
        result = await send_text_message(
            access_token=token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            text=text,
        )
    except WhatsAppGraphError as exc:
        return JSONResponse(
            status_code=502 if exc.retryable else 400,
            content={"success": False, "error": exc.code, "message": exc.message},
        )
    messages = result.get("messages") if isinstance(result, dict) else None
    wamid = None
    if isinstance(messages, list) and messages:
        wamid = str((messages[0] or {}).get("id") or "") or None
    return {"success": True, "provider_wamid": wamid, "to_wa_id_masked": f"…{to_wa_id[-4:]}"}


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
        from services.whatsapp_cloud.smart_followup.hooks import cancel_tenant_followups

        cancel_tenant_followups(db, tenant_id=session.tenant_id, reason="whatsapp_disconnected")
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
        waba_id = conn.waba_id
    try:
        templates = await list_message_templates(access_token=token, waba_id=waba_id)
    except WhatsAppGraphError as exc:
        return JSONResponse(status_code=502, content={"success": False, "error": exc.code, "message": exc.message})
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
async def whatsapp_create_template(
    connection_id: str, request: Request, body: dict[str, Any] = Body(default={})
) -> Any:
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
        repo.add_audit(
            tenant_id=session.tenant_id,
            connection_id=conn.id,
            actor_user_id=_actor_id(session),
            event_type="template_create_requested",
            detail={"name": name, "language": language, "category": category},
        )
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


@app.get("/api/whatsapp/cloud/pilot/list")
async def whatsapp_pilot_list(request: Request) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    flags = get_whatsapp_cloud_flags()
    try:
        with whatsapp_session() as db:
            repo = WhatsAppCloudRepository(db)
            rows = repo.list_pilots(status=None, limit=200)
            return {
                "success": True,
                "public_availability": flags.public_availability,
                "require_pilot_entitlement": flags.require_pilot_entitlement,
                "pilots": [
                    {
                        "tenant_id": r.tenant_id,
                        "status": r.status,
                        "reason": r.reason,
                        "granted_by_user_id": r.granted_by_user_id,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                        "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
                    }
                    for r in rows
                ],
                "config_keys_present": whatsapp_config_key_presence(),
            }
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE"})


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
        repo.add_audit(
            tenant_id=tenant_id,
            actor_user_id=_actor_id(session),
            event_type="pilot_revoked",
            detail={},
        )
        return {"success": True, "tenant_id": row.tenant_id, "status": row.status}


@app.get("/api/whatsapp/cloud/app-review/readiness")
async def whatsapp_app_review_readiness(request: Request) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    from services.whatsapp_cloud.app_review_readiness import build_app_review_readiness

    try:
        return build_app_review_readiness(tenant_id="linas")
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE"})


@app.get("/api/whatsapp/cloud/app-review/status")
async def whatsapp_app_review_status(request: Request) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    from services.whatsapp_cloud.app_review_bind import AppReviewBindError, status_app_review_bind

    try:
        return status_app_review_bind()
    except AppReviewBindError as exc:
        return JSONResponse(status_code=400, content={"success": False, "error": exc.code, "message": exc.message})
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE"})


@app.post("/api/whatsapp/cloud/app-review/bind")
async def whatsapp_app_review_bind(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    from services.whatsapp_cloud.app_review_bind import AppReviewBindError, bind_app_review_test_number

    tenant_id = str(body.get("tenant_id") or "").strip().lower()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    waba_id = str(body.get("waba_id") or "").strip()
    phone_number_id = str(body.get("phone_number_id") or "").strip()
    dry_run = bool(body.get("dry_run"))
    idempotency_key = str(body.get("idempotency_key") or "").strip() or None
    # Token must come from env META_WHATSAPP_APP_REVIEW_BIND_TOKEN — never from body logs.
    try:
        result = await bind_app_review_test_number(
            tenant_id=tenant_id,
            waba_id=waba_id,
            phone_number_id=phone_number_id,
            access_token=None,
            actor_user_id=_actor_id(session),
            idempotency_key=idempotency_key,
            dry_run=dry_run,
        )
        return result.public_dict()
    except AppReviewBindError as exc:
        return JSONResponse(status_code=400, content={"success": False, "error": exc.code, "message": exc.message})
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE"})


@app.post("/api/whatsapp/cloud/app-review/unbind")
async def whatsapp_app_review_unbind(request: Request, body: dict[str, Any] = Body(default={})) -> Any:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="platform_owner_required")
    from services.whatsapp_cloud.app_review_bind import AppReviewBindError, unbind_app_review_test_number

    tenant_id = str(body.get("tenant_id") or "").strip().lower()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id_required")
    connection_id = str(body.get("connection_id") or "").strip() or None
    idempotency_key = str(body.get("idempotency_key") or "").strip() or None
    try:
        result = unbind_app_review_test_number(
            tenant_id=tenant_id,
            actor_user_id=_actor_id(session),
            connection_id=connection_id,
            idempotency_key=idempotency_key,
        )
        return result.public_dict()
    except AppReviewBindError as exc:
        return JSONResponse(status_code=400, content={"success": False, "error": exc.code, "message": exc.message})
    except WhatsAppDatabaseUnavailable:
        return JSONResponse(status_code=503, content={"success": False, "error": "WHATSAPP_DB_UNAVAILABLE"})
