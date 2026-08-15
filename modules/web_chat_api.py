"""Public Web Chat widget API + authenticated mobile management."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Body, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from modules.api_security import _client_ip, require_permission, require_session
from modules.core import app
from services.rate_limit_service import rate_limit_service
from services.web_chat.embed import build_embed_snippet, public_api_base
from services.web_chat.processor import (
    WebChatError,
    default_greeting,
    evaluate_web_ai_eligibility,
    process_web_chat_message,
)
from services.web_chat.store import web_chat_store

_WIDGET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "web-chat", "widget.js")


class VisitorSessionBody(BaseModel):
    visitor_session_id: str = Field(min_length=8, max_length=80)
    widget_key: str = Field(min_length=8, max_length=120)
    language: str | None = None


class VisitorMessageBody(BaseModel):
    visitor_session_id: str = Field(min_length=8, max_length=80)
    widget_key: str = Field(min_length=8, max_length=120)
    content: str = Field(min_length=1, max_length=8000)
    language: str | None = None


class WebChatSettingsBody(BaseModel):
    site_url: str | None = None
    enabled: bool | None = None


def _rate_limit_widget(request: Request, *, session_id: str, widget_key: str) -> None:
    ip = _client_ip(request)
    for key, limit, window in (
        (f"web-chat:ip:{ip}", 60, 300),
        (f"web-chat:sid:{session_id}", 30, 300),
        (f"web-chat:key:{widget_key}", 120, 300),
    ):
        allowed, retry = rate_limit_service.hit(key, limit=limit, window_seconds=window)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"error": "Rate limit exceeded", "retry_after": retry},
                headers={"Retry-After": str(retry)},
            )


def _web_membership_gate(tenant_id: str) -> tuple[bool, str | None]:
    from services.membership.web_gate import WebPlanDenied, assert_web_plan_allowed

    try:
        assert_web_plan_allowed(tenant_id)
    except WebPlanDenied as exc:
        return False, str(exc)
    return True, None


def _widget_payload(widget: Any) -> dict[str, Any]:
    eligible, blocker = evaluate_web_ai_eligibility(widget.tenant_id, widget)
    return {
        "widget_key": widget.widget_key,
        "site_url": widget.site_url,
        "enabled": widget.enabled,
        "connected": widget.connected,
        "operational": eligible,
        "blocker_code": blocker,
        "embed_snippet": build_embed_snippet(widget_key=widget.widget_key),
        "widget_script_url": f"{public_api_base()}/web-chat/widget.js",
    }


@app.get("/web-chat/widget.js")
async def serve_web_chat_widget_js() -> FileResponse:
    if not os.path.isfile(_WIDGET_PATH):
        raise HTTPException(status_code=404, detail="Widget not found")
    return FileResponse(_WIDGET_PATH, media_type="application/javascript")


@app.post("/api/web-chat/session")
async def web_chat_bootstrap_session(
    request: Request,
    body: VisitorSessionBody,
    origin: str | None = Header(default=None, alias="Origin"),
) -> Any:
    widget = web_chat_store.get_widget_by_key(body.widget_key)
    if widget is None:
        raise HTTPException(status_code=404, detail={"error": "WIDGET_NOT_FOUND"})
    if not web_chat_store.origin_allowed_for_widget(widget, origin):
        raise HTTPException(status_code=403, detail={"error": "ORIGIN_NOT_ALLOWED"})
    _rate_limit_widget(request, session_id=body.visitor_session_id, widget_key=body.widget_key)
    greeting = default_greeting(body.language)
    session = web_chat_store.get_or_create_visitor(
        session_id=body.visitor_session_id,
        widget=widget,
        greeting=greeting,
    )
    return {
        "success": True,
        "session_id": session.id,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in session.messages
        ],
        "ai_available": evaluate_web_ai_eligibility(widget.tenant_id, widget)[0],
    }


@app.post("/api/web-chat/session/messages")
async def web_chat_send_message(
    request: Request,
    body: VisitorMessageBody,
    origin: str | None = Header(default=None, alias="Origin"),
) -> Any:
    widget = web_chat_store.get_widget_by_key(body.widget_key)
    if widget is None:
        raise HTTPException(status_code=404, detail={"error": "WIDGET_NOT_FOUND"})
    if not web_chat_store.origin_allowed_for_widget(widget, origin):
        raise HTTPException(status_code=403, detail={"error": "ORIGIN_NOT_ALLOWED"})
    _rate_limit_widget(request, session_id=body.visitor_session_id, widget_key=body.widget_key)
    visitor = web_chat_store.get_visitor(body.visitor_session_id)
    if visitor is None or visitor.widget_key != widget.widget_key:
        raise HTTPException(status_code=404, detail={"error": "SESSION_NOT_FOUND"})
    try:
        reply = await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text=body.content,
        )
    except WebChatError as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"success": False, "error": exc.code, "message": exc.message},
        )
    return {
        "success": True,
        "reply": reply,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in web_chat_store.get_visitor(body.visitor_session_id).messages  # type: ignore[union-attr]
        ],
    }


def _mobile_web_chat_payload(tenant_id: str, widget: Any) -> dict[str, Any]:
    membership_allows, membership_message = _web_membership_gate(tenant_id)
    payload = _widget_payload(widget)
    payload["membership_allows"] = membership_allows
    payload["membership_message"] = membership_message
    return payload


@app.get("/api/mobile/web-chat")
async def mobile_web_chat_settings(request: Request) -> Any:
    session = require_session(request)
    widget = web_chat_store.get_or_create_widget(session.tenant_id)
    return {"success": True, "web_chat": _mobile_web_chat_payload(session.tenant_id, widget)}


@app.put("/api/mobile/web-chat")
async def mobile_web_chat_update(request: Request, body: WebChatSettingsBody = Body(default={})) -> Any:
    session = require_permission(request, "settings")
    from services.membership.web_gate import WebPlanDenied, assert_web_plan_allowed

    try:
        assert_web_plan_allowed(session.tenant_id)
    except WebPlanDenied as exc:
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": exc.code, "message": str(exc)},
        )
    widget = web_chat_store.update_widget(
        session.tenant_id,
        site_url=body.site_url,
        enabled=body.enabled,
    )
    return {"success": True, "web_chat": _mobile_web_chat_payload(session.tenant_id, widget)}


@app.post("/api/mobile/web-chat/rotate-key")
async def mobile_web_chat_rotate_key(request: Request) -> Any:
    session = require_permission(request, "settings")
    from services.membership.web_gate import WebPlanDenied, assert_web_plan_allowed

    try:
        assert_web_plan_allowed(session.tenant_id)
    except WebPlanDenied as exc:
        return JSONResponse(
            status_code=403,
            content={"success": False, "error": exc.code, "message": str(exc)},
        )
    widget = web_chat_store.rotate_widget_key(session.tenant_id)
    return {"success": True, "web_chat": _mobile_web_chat_payload(session.tenant_id, widget)}
