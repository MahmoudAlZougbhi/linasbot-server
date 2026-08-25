"""Web Chat generate/deliver: worker runs AI; public HTTP only accepts + queues."""

from __future__ import annotations

from typing import Any


async def generate_web_chat_reply(*, tenant_id: str, payload: dict[str, Any]) -> tuple[str, str | None, str | None]:
    from services.web_chat.processor import process_web_chat_message
    from services.web_chat.store import web_chat_store

    session_id = str(payload.get("session_id") or "")
    widget = payload.get("widget")
    visitor = web_chat_store.get_visitor(session_id)
    if visitor is None or widget is None:
        return "", None, "session_missing"
    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text=str(payload.get("text") or ""),
        store=web_chat_store,
        idempotency_key=str(payload.get("idempotency_key") or "") or None,
    )
    reservation = str(payload.get("credit_reservation_id") or "") or None
    return str(reply or "").strip(), reservation, None


async def deliver_web_chat(snapshot: dict[str, Any]) -> dict[str, Any]:
    # Canonical reply is already appended by process_web_chat_message / poll outbox.
    return {
        "http_status": 200,
        "submitted": True,
        "message_id": str(snapshot.get("inbound_event_id") or snapshot.get("id") or ""),
    }
