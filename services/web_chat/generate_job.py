"""Run a previously accepted Web Chat turn off the public HTTP request."""

from __future__ import annotations

from typing import Any

from services.web_chat.processor import process_web_chat_message
from services.web_chat.store import web_chat_store


async def process_web_chat_generation_job(payload: dict[str, Any]) -> dict[str, Any]:
    from services.web_chat.config_models import WebChatWidgetConfig

    widget = payload.get("widget")
    if not isinstance(widget, WebChatWidgetConfig):
        raw = payload.get("widget_dict") or payload.get("widget")
        if not isinstance(raw, dict):
            return {"ok": False, "reason": "widget_missing"}
        widget = WebChatWidgetConfig(**raw)
    visitor = web_chat_store.get_visitor(str(payload.get("session_id") or ""))
    if visitor is None:
        return {"ok": False, "reason": "session_missing"}
    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text=str(payload.get("content") or payload.get("text") or ""),
        store=web_chat_store,
        idempotency_key=str(payload.get("idempotency_key") or "") or None,
    )
    return {"ok": True, "reply": reply}
