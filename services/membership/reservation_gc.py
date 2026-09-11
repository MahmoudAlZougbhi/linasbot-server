"""Reservation sweeper. Age or lease expiry never refunds a possible send."""

from __future__ import annotations

from datetime import UTC, datetime


def _created_at(raw: object) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        parsed = raw
    else:
        text = str(raw).strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def release_stale_reservations(*, max_age_seconds: int = 3600) -> int:
    from services.membership.reservation_reconcile import watch_stale_message_reservations

    return watch_stale_message_reservations(limit=50, max_age_seconds=max_age_seconds)


def run_reservation_gc() -> dict[str, int | bool | str]:
    from services.membership.reservation_reconcile import run_reservation_reconcile

    return run_reservation_reconcile()
