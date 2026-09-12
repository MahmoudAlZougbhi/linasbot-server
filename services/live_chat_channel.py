"""Resolve Live Chat inbox channel from index/source payloads. Never invents TikTok."""

from __future__ import annotations

from typing import Any

from utils.phone_utils import is_phone_like_user_id

LIVE_CHAT_CHANNELS = ("whatsapp", "instagram", "facebook", "tiktok", "web")

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
    "web": "web",
    "web_chat": "web",
    "website": "web",
}

_COMMENT_INBOX_CHANNELS = {
    "instagram": "instagram",
    "instagram_comment": "instagram",
    "facebook": "facebook",
    "facebook_comment": "facebook",
    "tiktok": "tiktok",
    "tiktok_comment": "tiktok",
}


def normalize_comment_inbox_channel(raw: Any) -> str | None:
    """Instagram / Facebook / TikTok comment surfaces only. Never WhatsApp or web."""
    key = str(raw or "").strip().lower()
    if not key:
        return None
    return _COMMENT_INBOX_CHANNELS.get(key)


_PREFIX_CHANNELS = {
    "web": "web",
    "tiktok": "tiktok",
    "instagram": "instagram",
    "facebook": "facebook",
    "messenger": "facebook",
    "whatsapp": "whatsapp",
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
    parts = [p for p in uid.split(":") if p]
    if not parts:
        return None
    if parts[0] in _PREFIX_CHANNELS:
        return _PREFIX_CHANNELS[parts[0]]
    if len(parts) >= 2 and parts[1] in _PREFIX_CHANNELS:
        return _PREFIX_CHANNELS[parts[1]]
    return None


def is_web_live_chat_user(user_id: str | None) -> bool:
    return _channel_from_user_id(user_id) == "web"


def is_whatsapp_live_chat_user_id(user_id: Any) -> bool:
    """Phone-like / WhatsApp ids only — never unlabeled web/tiktok/psid strings."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    if _channel_from_user_id(uid) == "whatsapp":
        return True
    if uid.startswith("+") and uid[1:].isdigit() and 8 <= len(uid[1:]) <= 15:
        return True
    return is_phone_like_user_id(uid)


def resolve_live_chat_channel(user_id: Any, payload: dict[str, Any] | None = None) -> str:
    """
    WhatsApp / Instagram / Facebook / TikTok / Web for inbox rows.
    user_id prefixes win. Unknown is never labeled WhatsApp. Never invents TikTok.
    """
    data: dict[str, Any] = payload or {}
    from_id = _channel_from_user_id(user_id) or _channel_from_user_id(data.get("user_id"))
    if from_id:
        return from_id
    customer_value = data.get("customer_info")
    customer: dict[str, Any] = customer_value if isinstance(customer_value, dict) else {}
    for raw in (
        data.get("channel"),
        customer.get("channel"),
        customer.get("platform"),
        data.get("platform"),
    ):
        ch = normalize_live_chat_channel(raw)
        if ch:
            return ch
    messages = data.get("recent_messages") or data.get("messages") or []
    if isinstance(messages, list) and messages:
        last: dict[str, Any] = messages[-1] if isinstance(messages[-1], dict) else {}
        metadata_value = last.get("metadata")
        meta: dict[str, Any] = metadata_value if isinstance(metadata_value, dict) else {}
        ch = normalize_live_chat_channel(meta.get("channel") or last.get("channel"))
        if ch:
            return ch
    if is_whatsapp_live_chat_user_id(user_id) or is_whatsapp_live_chat_user_id(data.get("user_id")):
        return "whatsapp"
    return "unknown"


def live_chat_channel_matches(chat: dict[str, Any], channel_filter: str) -> bool:
    wanted = normalize_live_chat_channel(channel_filter)
    if not wanted:
        return True
    return resolve_live_chat_channel(chat.get("user_id"), chat) == wanted


def live_chat_event_tenant_id(user_id: Any) -> str:
    """Tenant for SSE fanout. Prefixed social IDs carry the tenant; linas threads omit it."""
    uid = str(user_id or "").strip()
    parts = [p.strip() for p in uid.split(":") if p.strip()]
    if len(parts) >= 4 and parts[1].lower() in {"instagram", "facebook", "tiktok"}:
        return parts[0].lower()
    return "linas"


def coerce_live_chat_user_id(payload: dict[str, Any] | None, *, conversation_id: Any = None) -> str:
    """Never emit a blank user_id — mobile Zod drops those inbox rows."""
    data: dict[str, Any] = payload or {}
    customer_value = data.get("customer_info")
    customer: dict[str, Any] = customer_value if isinstance(customer_value, dict) else {}
    for raw in (
        data.get("user_id"),
        data.get("userId"),
        customer.get("user_id"),
        data.get("user_phone"),
        data.get("phone_number"),
        data.get("phone_clean"),
        customer.get("phone_full"),
        customer.get("phone_clean"),
        conversation_id,
        data.get("conversation_id"),
    ):
        value = str(raw or "").strip()
        if value and value.lower() not in {"none", "null", "undefined"}:
            return value
    return ""
