"""Fan out comment inbox updates on the Live Chat SSE bus (Redis HA)."""

from __future__ import annotations

import logging
from typing import Any

from services.live_chat_channel import normalize_comment_inbox_channel

COMMENT_SSE_EVENT = "comment_update"
_log = logging.getLogger("services.live_chat_comment_sse")


def comment_inbox_sse_payload(
    *,
    tenant_id: str,
    channel: str,
    post_id: str = "",
    comment_id: str = "",
    author: str = "",
    comment: str = "",
    ai_reply: str = "",
    delivery_status: str = "",
) -> dict[str, Any] | None:
    platform = normalize_comment_inbox_channel(channel)
    tenant = str(tenant_id or "").strip().lower()
    cid = str(comment_id or "").strip()
    if not tenant or not platform or not cid:
        return None
    payload: dict[str, Any] = {
        "tenant_id": tenant,
        "channel": platform,
        "platform": platform,
        "post_id": str(post_id or "").strip(),
        "comment_id": cid,
        "author": str(author or "").strip(),
        "comment": str(comment or "").strip(),
        "ai_reply": str(ai_reply or "").strip(),
        "delivery_status": str(delivery_status or "").strip(),
    }
    return payload


def schedule_comment_inbox_sse(
    *,
    tenant_id: str,
    channel: str,
    post_id: str = "",
    comment_id: str = "",
    author: str = "",
    comment: str = "",
    ai_reply: str = "",
    delivery_status: str = "",
) -> None:
    """Publish from webhook/worker sync code when an asyncio loop is running."""
    payload = comment_inbox_sse_payload(
        tenant_id=tenant_id,
        channel=channel,
        post_id=post_id,
        comment_id=comment_id,
        author=author,
        comment=comment,
        ai_reply=ai_reply,
        delivery_status=delivery_status,
    )
    if not payload:
        return
    try:
        import asyncio

        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_publish(payload))


async def _publish(payload: dict[str, Any]) -> None:
    try:
        from modules.live_chat_api_helpers import broadcast_sse_event

        await broadcast_sse_event(COMMENT_SSE_EVENT, payload)
    except Exception:
        _log.exception("comment inbox SSE broadcast failed")


def schedule_meta_comment_inbound(*, tenant_id: str, channel: str, event: dict[str, Any]) -> None:
    data = event if isinstance(event, dict) else {}
    schedule_comment_inbox_sse(
        tenant_id=tenant_id,
        channel=channel,
        post_id=str(data.get("post_id") or data.get("media_id") or ""),
        comment_id=str(data.get("comment_id") or ""),
        author=str(data.get("author_name") or data.get("author_username") or ""),
        comment=str(data.get("text") or ""),
        delivery_status="none",
    )
