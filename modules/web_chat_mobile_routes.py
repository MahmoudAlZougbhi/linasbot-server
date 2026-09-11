"""Authenticated mobile Web Chat management routes."""

from __future__ import annotations

from typing import Any

from fastapi import Body, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from modules.api_security import require_permission, require_session
from modules.core import app
from modules.web_chat_helpers import mobile_web_chat_payload
from services.web_chat.store import web_chat_store


class WebChatSettingsBody(BaseModel):
    site_url: str | None = None
    enabled: bool | None = None
    integration_mode: str | None = None
    appearance: dict[str, Any] | None = None


@app.get("/api/mobile/web-chat")
async def mobile_web_chat_settings(request: Request) -> Any:
    session = require_session(request)
    widget = web_chat_store.get_or_create_widget(session.tenant_id)
    return {"success": True, "web_chat": mobile_web_chat_payload(session.tenant_id, widget)}


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
    from services.membership.daily_edits import DailyEditLimitError
    from services.membership.edit_http import guarded_edit, limit_response

    disable = body.enabled is False
    try:
        with guarded_edit(
            tenant_id=session.tenant_id,
            kind="safety:web-chat-disable" if disable else "web-chat:settings",
            payload=body.model_dump(),
            safety=disable,
        ):
            widget = web_chat_store.update_widget(
                session.tenant_id,
                site_url=body.site_url,
                enabled=body.enabled,
                integration_mode=body.integration_mode,
                appearance=body.appearance,
            )
    except DailyEditLimitError as exc:
        return limit_response(exc)
    return {"success": True, "web_chat": mobile_web_chat_payload(session.tenant_id, widget)}


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
    from services.membership.edit_http import guarded_edit

    with guarded_edit(
        tenant_id=session.tenant_id,
        kind="safety:web-chat-rotate",
        payload={"action": "rotate_widget_key"},
        safety=True,
    ):
        widget = web_chat_store.rotate_widget_key(session.tenant_id)
    return {"success": True, "web_chat": mobile_web_chat_payload(session.tenant_id, widget)}


@app.post("/api/mobile/web-chat/check-installation")
async def mobile_web_chat_check_installation(request: Request) -> Any:
    session = require_permission(request, "settings")
    widget = web_chat_store.get_or_create_widget(session.tenant_id)
    return {
        "success": True,
        "installation_status": mobile_web_chat_payload(session.tenant_id, widget)["installation_status"],
        "installation": mobile_web_chat_payload(session.tenant_id, widget)["installation"],
    }
