"""Messaging window rules shared across DM channels (24h + safety buffer)."""

from __future__ import annotations

from datetime import UTC, datetime

from services.smart_followup.constants import CUSTOMER_SERVICE_WINDOW, SAFETY_BUFFER
from services.smart_followup.types import FollowUpConversationView


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def service_window_deadline(conv: FollowUpConversationView) -> datetime | None:
    opened = _aware(conv.service_window_opens_at or conv.last_inbound_at)
    if opened is None:
        return None
    return opened + CUSTOMER_SERVICE_WINDOW


def safe_send_deadline(conv: FollowUpConversationView) -> datetime | None:
    deadline = service_window_deadline(conv)
    if deadline is None:
        return None
    return deadline - SAFETY_BUFFER


def window_allows_send(*, conv: FollowUpConversationView, now: datetime | None = None) -> tuple[bool, str | None]:
    now = _aware(now) or datetime.now(UTC)
    opened = _aware(conv.service_window_opens_at or conv.last_inbound_at)
    if opened is None:
        return False, "service_window_unknown"
    if now < opened:
        return False, "clock_skew_before_window_open"
    hard_deadline = opened + CUSTOMER_SERVICE_WINDOW
    safe_deadline = hard_deadline - SAFETY_BUFFER
    if now >= hard_deadline:
        return False, "customer_service_window_expired"
    if now >= safe_deadline:
        return False, "safety_buffer_insufficient"
    return True, None


def remaining_safe_seconds(conv: FollowUpConversationView, *, now: datetime | None = None) -> int | None:
    now = _aware(now) or datetime.now(UTC)
    safe = safe_send_deadline(conv)
    if safe is None:
        return None
    return int((safe - now).total_seconds())
