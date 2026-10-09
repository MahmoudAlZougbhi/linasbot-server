"""Store relative dates as absolute dates in the tenant's calendar."""

from __future__ import annotations

from datetime import date, timedelta

_WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def absolute_weekday(text: str, *, today: date) -> date | None:
    """Resolve 'next <weekday>' to a date after today. Other text is left alone."""
    words = (text or "").casefold().split()
    if len(words) < 2 or words[0] != "next":
        return None
    target = _WEEKDAYS.get(words[1])
    if target is None:
        return None
    delta = (target - today.weekday()) % 7
    if delta == 0:
        delta = 7
    return today + timedelta(days=delta)


def date_needs_refresh(stored: date, *, today: date) -> bool:
    return stored < today


def missing_request_fields(required: list[str], collected: dict[str, str]) -> list[str]:
    have = {key for key, value in collected.items() if str(value or "").strip()}
    return [key for key in required if key not in have]
