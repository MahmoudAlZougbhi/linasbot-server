"""Which Live Chat / Comments channels a team member may see."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from modules.api_security import resolve_permissions
from services.dashboard_session_service import SessionRecord
from services.live_chat_channel import resolve_live_chat_channel

CHANNEL_PERMISSIONS: dict[str, str] = {
    "channelWhatsapp": "whatsapp",
    "channelInstagram": "instagram",
    "channelFacebook": "facebook",
    "channelTiktok": "tiktok",
    "channelWeb": "web",
}

_PRIVILEGED = frozenset({"admin", "owner", "platform_owner"})


def allowed_channels_for_session(session: SessionRecord) -> frozenset[str] | None:
    """None means every channel. Otherwise only the listed channel ids."""
    role = str(session.role or "").strip().lower()
    if role in _PRIVILEGED:
        return None
    perms = resolve_permissions(role, session.permissions)
    return frozenset(channel for key, channel in CHANNEL_PERMISSIONS.items() if perms.get(key))


def session_can_use_channel(session: SessionRecord, channel: str) -> bool:
    allowed = allowed_channels_for_session(session)
    if allowed is None:
        return True
    return str(channel or "").strip().lower() in allowed


def require_session_channel(session: SessionRecord, user_id: str, payload: dict[str, Any] | None = None) -> None:
    channel = resolve_live_chat_channel(user_id, payload)
    if not session_can_use_channel(session, channel):
        raise HTTPException(status_code=403, detail="Forbidden")


def effective_inbox_channel(session: SessionRecord, requested: str) -> str | None:
    """Channel query for the inbox. None means the caller should return an empty page."""
    wanted = str(requested or "all").strip().lower() or "all"
    allowed = allowed_channels_for_session(session)
    if allowed is None:
        return wanted
    if wanted != "all":
        return wanted if wanted in allowed else None
    if len(allowed) == 1:
        return next(iter(allowed))
    return "all"


def filter_chats_for_session(session: SessionRecord, payload: dict[str, Any]) -> dict[str, Any]:
    allowed = allowed_channels_for_session(session)
    if allowed is None:
        return payload
    chats = [
        row for row in (payload.get("chats") or []) if resolve_live_chat_channel(row.get("user_id"), row) in allowed
    ]
    next_payload = dict(payload)
    next_payload["chats"] = chats
    return next_payload
