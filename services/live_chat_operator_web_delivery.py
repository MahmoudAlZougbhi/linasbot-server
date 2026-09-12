"""Deliver Live Chat operator text to website visitors via the Web Chat outbox."""

from __future__ import annotations

from typing import Any

from services.live_chat_channel import is_web_live_chat_user
from services.web_chat.constants import USER_ID_PREFIX


def parse_web_visitor_session_id(user_id: str, conversation_id: str | None = None) -> str:
    """Visitor session id from `web:{session}` or conversation `web:{tenant}:{session}`."""
    uid = str(user_id or "").strip()
    prefix = USER_ID_PREFIX.lower()
    if uid.lower().startswith(prefix):
        rest = uid.split(":", 1)[1].strip()
        if rest:
            return rest
    cid = str(conversation_id or "").strip()
    if cid:
        from services.customer_ai.history_web import session_id_from_conversation

        sid = session_id_from_conversation(cid).strip()
        if sid and sid != cid:
            return sid
        if cid.lower().startswith(prefix):
            parts = cid.split(":", 2)
            if len(parts) == 3 and parts[2].strip():
                return parts[2].strip()
    raise ValueError("unsupported_web_live_chat_user_id")


def web_operator_media_not_supported() -> dict[str, Any]:
    return {
        "success": False,
        "delivered": False,
        "error": "Web Chat operator media replies are not supported",
        "channel": "web",
    }


def deliver_web_operator_text(
    *,
    user_id: str,
    conversation_id: str,
    text: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Enqueue operator text on the visitor outbox. Never calls WhatsApp."""
    body = str(text or "").strip()
    if not body:
        return {"success": False, "delivered": False, "error": "empty_message", "channel": "web"}
    if not is_web_live_chat_user(user_id):
        return {"success": False, "delivered": False, "error": "not_web_live_chat_user", "channel": "web"}
    try:
        session_id = parse_web_visitor_session_id(user_id, conversation_id)
    except ValueError as exc:
        return {"success": False, "delivered": False, "error": str(exc), "channel": "web"}

    from services.web_chat.store import web_chat_store

    key = str(idempotency_key or "").strip() or None
    try:
        queued = web_chat_store.queue_assistant_message(session_id, body, idempotency_key=key)
    except KeyError:
        return {
            "success": False,
            "delivered": False,
            "error": "web_session_not_found",
            "channel": "web",
        }
    except Exception as exc:
        return {
            "success": False,
            "delivered": False,
            "error": f"web_outbox_enqueue_failed: {exc}",
            "channel": "web",
        }
    # False means the idempotency key was already claimed — already queued.
    return {
        "success": True,
        "delivered": True,
        "channel": "web",
        "duplicate": queued is False,
    }
