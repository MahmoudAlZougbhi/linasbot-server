"""Public Web Chat widget routes."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Header, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from modules.core import app
from modules.web_chat_helpers import (
    assert_origin_allowed,
    rate_limit_widget,
    resolve_widget_or_404,
)
from services.web_chat.processor import (
    WebChatError,
    default_greeting,
    evaluate_web_ai_eligibility,
    process_web_chat_message,
)
from services.web_chat.public_config import build_public_widget_config
from services.web_chat.store import web_chat_store

_WIDGET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "public", "web-chat")
_WIDGET_PATH = os.path.join(_WIDGET_DIR, "widget.js")


class VisitorSessionBody(BaseModel):
    visitor_session_id: str = Field(min_length=8, max_length=80)
    widget_key: str = Field(min_length=8, max_length=120)
    language: str | None = None


class VisitorMessageBody(BaseModel):
    visitor_session_id: str = Field(min_length=8, max_length=80)
    widget_key: str = Field(min_length=8, max_length=120)
    content: str = Field(min_length=1, max_length=8000)
    language: str | None = None


class HeartbeatBody(BaseModel):
    widget_key: str = Field(min_length=8, max_length=120)


@app.get("/web-chat/widget.js")
async def serve_web_chat_widget_js() -> FileResponse:
    if not os.path.isfile(_WIDGET_PATH):
        raise HTTPException(status_code=404, detail="Widget not found")
    return FileResponse(_WIDGET_PATH, media_type="application/javascript")


@app.get("/web-chat/sdk-docs")
async def web_chat_sdk_docs() -> PlainTextResponse:
    text = (
        "# Linas Website Chat SDK\n\n"
        "Use your public integration ID (widget_key) with the browser endpoints:\n\n"
        "1. POST /api/web-chat/session — bootstrap visitor session\n"
        "2. POST /api/web-chat/session/messages — send a visitor message\n"
        "3. GET /api/web-chat/config?widget_key=... — read public chat config\n"
        "4. POST /api/web-chat/heartbeat — report installation (built-in chat mode)\n\n"
        "Always send the Origin header from your allowed domain. "
        "Server-to-server keys are planned; use the public integration ID for browser clients only.\n"
    )
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8")


@app.get("/web-chat/{asset_name}")
async def serve_web_chat_asset(asset_name: str) -> FileResponse:
    safe = os.path.basename(asset_name)
    if safe in {"widget.js", "sdk-docs"}:
        raise HTTPException(status_code=404, detail="Asset not found")
    path = os.path.join(_WIDGET_DIR, safe)
    if not os.path.isfile(path) or not safe.endswith(".js"):
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path, media_type="application/javascript")


@app.get("/api/web-chat/sdk-docs")
async def web_chat_sdk_docs_api() -> PlainTextResponse:
    return await web_chat_sdk_docs()


@app.get("/api/web-chat/config")
async def web_chat_public_config(
    widget_key: str = Query(min_length=8, max_length=120),
    origin: str | None = Header(default=None, alias="Origin"),
) -> Any:
    widget = resolve_widget_or_404(widget_key)
    if not widget.enabled:
        return JSONResponse(status_code=403, content={"success": False, "error": "WIDGET_DISABLED"})
    if widget.site_url and origin and not web_chat_store.origin_allowed_for_widget(widget, origin):
        return JSONResponse(status_code=403, content={"success": False, "error": "ORIGIN_NOT_ALLOWED"})
    return {"success": True, "config": build_public_widget_config(widget)}


@app.post("/api/web-chat/heartbeat")
async def web_chat_heartbeat(
    request: Request,
    body: HeartbeatBody,
    origin: str | None = Header(default=None, alias="Origin"),
) -> Any:
    widget = resolve_widget_or_404(body.widget_key)
    assert_origin_allowed(widget, origin)
    rate_limit_widget(request, session_id="heartbeat", widget_key=body.widget_key)
    updated = web_chat_store.record_installation_heartbeat(widget, origin=origin)
    return {
        "success": True,
        "installation": {
            "last_seen_at": updated.installation.last_seen_at,
            "last_origin": updated.installation.last_origin,
        },
    }


@app.post("/api/web-chat/session")
async def web_chat_bootstrap_session(
    request: Request,
    body: VisitorSessionBody,
    origin: str | None = Header(default=None, alias="Origin"),
) -> Any:
    widget = resolve_widget_or_404(body.widget_key)
    assert_origin_allowed(widget, origin)
    rate_limit_widget(request, session_id=body.visitor_session_id, widget_key=body.widget_key)
    greeting = default_greeting(body.language, widget)
    session = web_chat_store.get_or_create_visitor(
        session_id=body.visitor_session_id,
        widget=widget,
        greeting=greeting,
    )
    eligible, _blocker = evaluate_web_ai_eligibility(widget.tenant_id, widget)
    return {
        "success": True,
        "session_id": session.id,
        "channel": "web",
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in session.messages
        ],
        "ai_available": eligible,
        "config": build_public_widget_config(widget, eligible=eligible),
    }


@app.post("/api/web-chat/session/messages")
async def web_chat_send_message(
    request: Request,
    body: VisitorMessageBody,
    origin: str | None = Header(default=None, alias="Origin"),
) -> Any:
    widget = resolve_widget_or_404(body.widget_key)
    assert_origin_allowed(widget, origin)
    rate_limit_widget(request, session_id=body.visitor_session_id, widget_key=body.widget_key)
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
    refreshed = web_chat_store.get_visitor(body.visitor_session_id)
    return {
        "success": True,
        "channel": "web",
        "reply": reply,
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at}
            for m in (refreshed.messages if refreshed else [])
        ],
    }
