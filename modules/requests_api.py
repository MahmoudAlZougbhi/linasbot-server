"""FastAPI routes for Customer Requests (Expo operator product)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Query, Request

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from modules.core import app
from services.requests.permissions import (
    can_view_sensitive,
    require_requests_manage,
    require_requests_manual_chat,
    require_requests_notify,
    require_requests_view,
)
from services.requests.schemas import (
    RequestAssignBody,
    RequestCreateBody,
    RequestFinalActionBody,
    RequestManualModeBody,
    RequestManualSendBody,
    RequestNoteBody,
    RequestNotifyRetryBody,
    RequestStatusBody,
)
from services.requests.service import CustomerRequestsError, CustomerRequestsService


def _tenant(session: Any) -> str:
    tenant_id = str(getattr(session, "tenant_id", "") or "").strip()
    if not tenant_id:
        raise HTTPException(status_code=403, detail="tenant required")
    return tenant_id


def _actor(session: Any) -> str:
    return str(getattr(session, "user_id", "") or getattr(session, "id", "") or "").strip() or "unknown"


def _http(exc: CustomerRequestsError) -> HTTPException:
    return HTTPException(status_code=exc.http_status, detail={"code": exc.code, "message": exc.message})


def _db_cm() -> Any:
    try:
        return whatsapp_session()
    except WhatsAppDatabaseUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "REQUESTS_DB_UNAVAILABLE", "message": str(exc)},
        ) from exc


@app.get("/api/requests/setup-status")
def requests_setup_status(request: Request) -> dict[str, Any]:
    session = require_requests_view(request)
    tenant_id = _tenant(session)
    from services.requests.config_loader import (
        load_published_requests_config,
        requests_capture_active,
    )

    cfg = load_published_requests_config(tenant_id)
    active = requests_capture_active(tenant_id)
    return {
        "setup_required": not active,
        "module_enabled": bool(cfg.get("module_enabled")) if cfg else False,
        "enabled_types": list(cfg.get("enabled_types") or []) if cfg else [],
        "capture_active": active,
    }


@app.get("/api/requests")
def list_requests(
    request: Request,
    request_type: str | None = None,
    status: str | None = None,
    source_channel: str | None = None,
    assigned_user_id: str | None = None,
    q: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
) -> dict[str, Any]:
    session = require_requests_view(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).list(
                tenant_id=tenant_id,
                request_type=request_type,
                status=status,
                source_channel=source_channel,
                assigned_user_id=assigned_user_id,
                q=q,
                cursor=cursor,
                limit=limit,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.get("/api/requests/{request_id}")
def get_request(request_id: str, request: Request) -> dict[str, Any]:
    session = require_requests_view(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).get(
                tenant_id=tenant_id,
                request_id=request_id,
                include_sensitive=can_view_sensitive(session),
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests")
def create_request(body: RequestCreateBody, request: Request) -> dict[str, Any]:
    """Internal/operator-assisted create path (AI tool uses the same service)."""
    session = require_requests_manage(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).create_from_ai(tenant_id=tenant_id, body=body)
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests/{request_id}/assign")
def assign_request(request_id: str, body: RequestAssignBody, request: Request) -> dict[str, Any]:
    session = require_requests_manage(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).assign(
                tenant_id=tenant_id,
                request_id=request_id,
                actor_user_id=_actor(session),
                assigned_user_id=body.assigned_user_id,
                row_version=body.row_version,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests/{request_id}/notes")
def add_request_note(request_id: str, body: RequestNoteBody, request: Request) -> dict[str, Any]:
    session = require_requests_manage(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).add_note(
                tenant_id=tenant_id,
                request_id=request_id,
                author_user_id=_actor(session),
                body=body.body,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests/{request_id}/status")
def change_request_status(request_id: str, body: RequestStatusBody, request: Request) -> dict[str, Any]:
    session = require_requests_manage(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).transition_status(
                tenant_id=tenant_id,
                request_id=request_id,
                actor_user_id=_actor(session),
                to_status=body.to_status,
                row_version=body.row_version,
                cancellation_reason=body.cancellation_reason,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests/{request_id}/final-action")
def request_final_action(
    request_id: str, body: RequestFinalActionBody, request: Request
) -> dict[str, Any]:
    session = require_requests_notify(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).final_action(
                tenant_id=tenant_id,
                request_id=request_id,
                actor_user_id=_actor(session),
                action=body.action,
                row_version=body.row_version,
                completion_message=body.completion_message,
                idempotency_key=body.idempotency_key,
                send_notification=body.send_notification,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests/{request_id}/notify-retry")
def retry_request_notification(
    request_id: str, body: RequestNotifyRetryBody, request: Request
) -> dict[str, Any]:
    session = require_requests_notify(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            return CustomerRequestsService(db).retry_notification(
                tenant_id=tenant_id,
                request_id=request_id,
                actor_user_id=_actor(session),
                idempotency_key=body.idempotency_key,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc


@app.post("/api/requests/{request_id}/manual-mode/resume")
async def resume_request_manual_mode(
    request_id: str, body: RequestManualModeBody, request: Request
) -> dict[str, Any]:
    session = require_requests_manual_chat(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            row = CustomerRequestsService(db).get(
                tenant_id=tenant_id,
                request_id=request_id,
                include_sensitive=False,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc
        conversation_id = str(row.get("conversation_id") or row.get("manual_mode_conversation_ref") or "")
        if not conversation_id:
            raise HTTPException(
                status_code=409, detail={"code": "NO_CONVERSATION", "message": "Request has no conversation"}
            )
        from services.requests.manual_mode import resume_manual_mode

        result = await resume_manual_mode(
            conversation_id=conversation_id,
            user_id=body.user_id,
            actor_user_id=_actor(session),
            tenant_id=tenant_id,
            request_id=request_id,
            source_channel=row.get("source_channel"),
            session=db,
        )
        db.commit()
        return {
            "success": True,
            "conversation_id": result.conversation_id,
            "control_epoch": result.control_epoch,
            "already_active": result.already_active,
            "audit_recorded": result.audit_recorded,
        }


@app.post("/api/requests/{request_id}/manual-chat/send")
async def send_request_manual_chat(request_id: str, body: RequestManualSendBody, request: Request) -> dict[str, Any]:
    """Text reply on the request conversation — pauses AI first (server-authoritative)."""
    session = require_requests_manual_chat(request)
    tenant_id = _tenant(session)
    with _db_cm() as db:
        try:
            row = CustomerRequestsService(db).get(
                tenant_id=tenant_id,
                request_id=request_id,
                include_sensitive=False,
            )
        except CustomerRequestsError as exc:
            raise _http(exc) from exc
        conversation_id = str(row.get("conversation_id") or "")
        if not conversation_id:
            raise HTTPException(
                status_code=409, detail={"code": "NO_CONVERSATION", "message": "Request has no conversation"}
            )

    from services.live_chat_service import live_chat_service
    from services.whatsapp_adapters.whatsapp_factory import WhatsAppFactory

    adapter = WhatsAppFactory.get_adapter(WhatsAppFactory.get_current_provider())
    return await live_chat_service.send_operator_message(
        conversation_id=conversation_id,
        user_id=body.user_id,
        message=body.message,
        operator_id=_actor(session),
        adapter=adapter,
        message_type="text",
        idempotency_key=body.idempotency_key,
        tenant_id=tenant_id,
        operator_name=getattr(session, "email", None),
        request_id=request_id,
        source_channel=row.get("source_channel"),
    )
