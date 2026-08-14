"""Resolve Live Chat inbox channel from index/source payloads. Never invents TikTok."""

from __future__ import annotations

from typing import Any

LIVE_CHAT_CHANNELS = ("whatsapp", "instagram", "facebook", "tiktok")

_ALIASES = {
    "whatsapp": "whatsapp",
    "whatsapp_cloud": "whatsapp",
    "wa": "whatsapp",
    "instagram": "instagram",
    "instagram_dm": "instagram",
    "ig": "instagram",
    "facebook": "facebook",
    "facebook_messenger": "facebook",
    "messenger": "facebook",
    "tiktok": "tiktok",
}


def normalize_live_chat_channel(raw: Any) -> str | None:
    """Return a canonical inbox channel, or None when the value is empty/unknown/all."""
    key = str(raw or "").strip().lower()
    if not key or key == "all":
        return None
    return _ALIASES.get(key)


def _channel_from_user_id(user_id: Any) -> str | None:
    uid = str(user_id or "").strip().lower()
    if not uid:
        return None
    if "tiktok:" in uid:
        return "tiktok"
    if "instagram:" in uid:
        return "instagram"
    if "facebook:" in uid or "messenger:" in uid:
        return "facebook"
    if "whatsapp:" in uid:
        return "whatsapp"
    return None


def resolve_live_chat_channel(user_id: Any, payload: dict[str, Any] | None = None) -> str:
    """
    WhatsApp / Instagram / Facebook / TikTok for inbox rows.
    TikTok only when the payload or user_id actually says TikTok — never as a default.
    """
    data = payload or {}
    customer = data.get("customer_info") if isinstance(data.get("customer_info"), dict) else {}
    for raw in (
        data.get("channel"),
        customer.get("channel"),
        customer.get("platform"),
        data.get("platform"),
    ):
        ch = normalize_live_chat_channel(raw)
        if ch:
            return ch
    from_id = _channel_from_user_id(user_id) or _channel_from_user_id(data.get("user_id"))
    if from_id:
        return from_id
    messages = data.get("recent_messages") or data.get("messages") or []
    if isinstance(messages, list) and messages:
        last = messages[-1] if isinstance(messages[-1], dict) else {}
        meta = last.get("metadata") if isinstance(last.get("metadata"), dict) else {}
        ch = normalize_live_chat_channel(meta.get("channel") or last.get("channel"))
        if ch:
            return ch
    return "whatsapp"


def live_chat_channel_matches(chat: dict[str, Any], channel_filter: str) -> bool:
    wanted = normalize_live_chat_channel(channel_filter)
    if not wanted:
        return True
    return resolve_live_chat_channel(chat.get("user_id"), chat) == wanted
