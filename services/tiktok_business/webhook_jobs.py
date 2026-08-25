"""Process claimed TikTok webhook events off the HTTP request."""

from __future__ import annotations

from typing import Any


async def process_claimed_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    event_name = str(payload.get("event_name") or "").strip().lower()
    event_id = str(payload.get("event_id") or "")
    body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
    content = payload.get("content") if isinstance(payload.get("content"), dict) else {}
    if event_name in {"im_receive_msg", "im_send_msg", "direct_message", "im_mark_read_msg"}:
        from services.tiktok_business.messaging import handle_messaging_webhook

        return await handle_messaging_webhook(payload=body, content=content, event_name=event_name, event_id=event_id)
    if event_name.startswith("comment."):
        from services.tiktok_business.comment_webhook import handle_comment_webhook

        return await handle_comment_webhook(payload=body, content=content, event_name=event_name)
    return {"accepted": 1, "ignored": True, "event": event_name or "unknown"}
