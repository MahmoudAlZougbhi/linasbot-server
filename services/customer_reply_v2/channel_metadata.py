"""Typed channel metadata for Luna and Tera (DM vs comment, public vs private)."""

from __future__ import annotations

from typing import Any


def parse_channel(channel: str) -> tuple[str, str, bool]:
    """Return (platform, surface, is_public) from a Customer Reply channel kind."""
    ch = (channel or "").strip().lower()
    if "comment" in ch:
        surface = "comment"
        is_public = True
    else:
        surface = "dm"
        is_public = False
    if "facebook" in ch or ch in {"fb", "messenger", "page", "facebook_messenger"}:
        platform = "facebook"
    elif "whatsapp" in ch:
        platform = "whatsapp"
    elif "web" in ch:
        platform = "web"
    else:
        platform = "instagram"
    return platform, surface, is_public


def build_channel_metadata(
    *,
    channel: str,
    account_id: str = "",
    post_id: str = "",
    comment_id: str = "",
    message_id: str = "",
    conversation_id: str = "",
    reply_to: dict[str, Any] | str | None = None,
    can_reply_publicly: bool | None = None,
    can_send_dm: bool | None = None,
    max_media_items: int | None = None,
) -> dict[str, Any]:
    platform, surface, is_public = parse_channel(channel)
    if can_reply_publicly is None:
        can_reply_publicly = is_public
    if can_send_dm is None:
        can_send_dm = True
    if max_media_items is None:
        max_media_items = 0 if is_public else 10
    reply_obj: dict[str, Any] | None
    if reply_to is None or reply_to == "":
        reply_obj = None
    elif isinstance(reply_to, dict):
        reply_obj = dict(reply_to)
    else:
        reply_obj = {"message_id": str(reply_to)}
    return {
        "platform": platform,
        "surface": surface,
        "is_public": is_public,
        "account_id": str(account_id or "").strip(),
        "post_id": str(post_id or "").strip(),
        "comment_id": str(comment_id or "").strip(),
        "message_id": str(message_id or "").strip(),
        "conversation_id": str(conversation_id or "").strip(),
        "reply_to": reply_obj,
        "channel_capabilities": {
            "can_reply_publicly": bool(can_reply_publicly),
            "can_send_dm": bool(can_send_dm),
            "max_media_items": int(max_media_items),
        },
        "legacy_channel": channel,
    }
