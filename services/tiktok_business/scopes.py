"""Map granted TikTok scopes to Comments vs DM capabilities. Never mark active without scopes."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.config import (
    COMMENT_MANAGE_SCOPES,
    COMMENT_READ_SCOPES,
    MEDIA_SCOPES,
    MESSAGING_READ_SCOPES,
    MESSAGING_SEND_SCOPES,
    PROFILE_SCOPES,
    REQUESTED_SCOPES,
    parse_scope_string,
)


def as_scope_set(raw: Any) -> set[str]:
    if isinstance(raw, (list, tuple, set, frozenset)):
        return {str(item).strip() for item in raw if str(item).strip()}
    return set(parse_scope_string(str(raw or "")))


def comments_read_ready(granted: Any) -> bool:
    have = as_scope_set(granted)
    return bool(have & COMMENT_READ_SCOPES) and bool(have & MEDIA_SCOPES)


def comments_manage_ready(granted: Any) -> bool:
    have = as_scope_set(granted)
    return comments_read_ready(have) and bool(have & COMMENT_MANAGE_SCOPES)


def profile_ready(granted: Any) -> bool:
    return bool(as_scope_set(granted) & PROFILE_SCOPES)


def messaging_read_ready(granted: Any) -> bool:
    return bool(as_scope_set(granted) & MESSAGING_READ_SCOPES)


def messaging_send_ready(granted: Any) -> bool:
    have = as_scope_set(granted)
    return bool(have & MESSAGING_READ_SCOPES) and bool(have & MESSAGING_SEND_SCOPES)


def missing_requested(granted: Any) -> list[str]:
    have = as_scope_set(granted)
    return [scope for scope in REQUESTED_SCOPES if scope not in have]


def comments_status(*, granted: Any, connected: bool, token_expired: bool, error: bool) -> str:
    if error:
        return "error"
    if not connected:
        return "disconnected"
    if token_expired:
        return "token_expired"
    if comments_manage_ready(granted):
        return "connected"
    if comments_read_ready(granted):
        return "permission_required"
    return "permission_required"


def dm_status(*, granted: Any, connected: bool, token_expired: bool, error: bool) -> str:
    if error:
        return "error"
    if not connected:
        return "disconnected"
    if token_expired:
        return "token_expired"
    if messaging_send_ready(granted):
        return "connected"
    return "permission_pending"
