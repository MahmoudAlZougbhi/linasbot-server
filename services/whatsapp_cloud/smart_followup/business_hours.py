"""Business-hours gate using published CM opening_hours (authoritative)."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_DAY_ATTRS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


def _parse_hhmm(value: str) -> time | None:
    raw = (value or "").strip()
    if not raw or ":" not in raw:
        return None
    parts = raw.split(":")
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except (TypeError, ValueError):
        return None
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        return None
    return time(hour=hour, minute=minute)


def _resolve_timezone(sections: dict[str, Any]) -> ZoneInfo:
    tz_name = "Asia/Beirut"
    off_days = sections.get("off_days") or {}
    if isinstance(off_days, dict):
        candidate = str(off_days.get("timezone") or "").strip()
        if candidate:
            tz_name = candidate
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _schedule_open_now(schedule: Any, local_now: datetime) -> bool:
    day_name = _DAY_ATTRS[local_now.weekday()]
    day = getattr(schedule, day_name, None)
    if day is None and isinstance(schedule, dict):
        day = schedule.get(day_name)
    if day is None:
        return False
    closed = bool(getattr(day, "closed", None) if not isinstance(day, dict) else day.get("closed"))
    if closed:
        return False
    open_s = getattr(day, "open", None) if not isinstance(day, dict) else day.get("open")
    close_s = getattr(day, "close", None) if not isinstance(day, dict) else day.get("close")
    open_t = _parse_hhmm(str(open_s or ""))
    close_t = _parse_hhmm(str(close_s or ""))
    if open_t is None or close_t is None:
        return False
    current = local_now.timetz().replace(tzinfo=None)
    if open_t <= close_t:
        return open_t <= current < close_t
    # Overnight window (e.g. 22:00–02:00).
    return current >= open_t or current < close_t


def is_within_business_hours(*, tenant_id: str, now: datetime | None = None) -> tuple[bool, str | None]:
    """True when at least one published opening_hours schedule is open now.

    If opening hours are missing/empty, fail closed with an explicit reason
    (do not silently send outside hours when the toggle is ON).
    """
    now_utc = now if now is not None else datetime.now(UTC)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)

    try:
        from services.cm.schemas import OpeningHoursSection
        from services.cm.version_store import load_published_content

        _pointer, sections = load_published_content(tenant_id)
    except Exception:
        return False, "opening_hours_unavailable"

    raw = (sections or {}).get("opening_hours") if isinstance(sections, dict) else None
    if not raw:
        return False, "opening_hours_missing"

    try:
        section = raw if isinstance(raw, OpeningHoursSection) else OpeningHoursSection.model_validate(raw)
    except Exception:
        return False, "opening_hours_invalid"

    if not section.items:
        return False, "opening_hours_empty"

    tz = _resolve_timezone(sections if isinstance(sections, dict) else {})
    local_now = now_utc.astimezone(tz)
    for schedule in section.items:
        if _schedule_open_now(schedule, local_now):
            return True, None
    return False, "outside_business_hours"
