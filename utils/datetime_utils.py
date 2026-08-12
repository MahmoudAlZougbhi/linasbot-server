"""Date and time helpers for booking logic (fixed UTC+0200).

Intent patterns/detectors: datetime_intents (LOC split).
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from utils.datetime_intents import (  # noqa: F401
    detect_appointment_inquiry_intent,
    detect_bulk_reschedule_all_intent,
    detect_day_reference,
    detect_existing_appointment_edit_intent,
    detect_last_weekday_intent_from_user_text,
    detect_relative_intent,
    detect_reschedule_intent,
    text_mentions_datetime,
)

BOT_FIXED_TZ = datetime.timezone(datetime.timedelta(hours=2), name="+0200")


def now_in_bot_tz() -> datetime.datetime:
    """Return current aware datetime in fixed +0200 timezone."""
    return datetime.datetime.now(BOT_FIXED_TZ)


def to_bot_tz(dt: datetime.datetime) -> datetime.datetime:
    """Convert datetime to fixed +0200 timezone (assume +0200 if naive)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=BOT_FIXED_TZ)
    return dt.astimezone(BOT_FIXED_TZ)


def parse_datetime_flexible(date_value: str) -> datetime.datetime | None:
    """
    Parse flexible date strings into aware +0200 datetime.
    Supports common GPT outputs and ISO strings with timezone offsets.
    """
    if date_value is None:
        return None

    value = str(date_value).strip()
    if not value:
        return None

    # Handle ISO with "Z"
    iso_value = value.replace("Z", "+00:00")

    # Try ISO parser first (handles offsets)
    try:
        dt = datetime.datetime.fromisoformat(iso_value)
        dt = to_bot_tz(dt)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            dt = dt.replace(hour=10, minute=0, second=0, microsecond=0)
        return dt
    except ValueError:
        pass

    # Try explicit formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %I:%M:%S %p", "%d/%m/%Y %H:%M:%S"):
        try:
            parsed = datetime.datetime.strptime(value, fmt)
            return parsed.replace(tzinfo=BOT_FIXED_TZ, microsecond=0)
        except ValueError:
            continue

    # Date only
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            parsed = datetime.datetime.strptime(value, fmt)
            parsed = parsed.replace(hour=10, minute=0, second=0, microsecond=0)
            return parsed.replace(tzinfo=BOT_FIXED_TZ)
        except ValueError:
            continue

    return None


def datetime_from_ai_date_components(raw: Any) -> datetime.datetime | None:
    """
    Build a single aware datetime in BOT_FIXED_TZ from structured fields the model sends
    (year, month, day, hour, optional minute). Prefer this over a free-form `date` string when
    the user said vague weekday phrases (الخميس الجاي، الجمعة الجاي…) so the model must pick
    one concrete civil date.
    """
    if not isinstance(raw, dict):
        return None

    def _ci(v: Any) -> int | None:
        if v is None:
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    y = _ci(raw.get("year"))
    m = _ci(raw.get("month"))
    d = _ci(raw.get("day"))
    h = _ci(raw.get("hour"))
    mi = _ci(raw.get("minute"))
    if mi is None:
        mi = 0
    if y is None or m is None or d is None or h is None:
        return None
    if not (1 <= m <= 12 and 1 <= d <= 31 and 0 <= h <= 23 and 0 <= mi <= 59):
        return None
    if y < 2000 or y > 2100:
        return None
    try:
        return datetime.datetime(y, m, d, h, mi, 0, tzinfo=BOT_FIXED_TZ, microsecond=0)
    except ValueError:
        return None


def resolve_relative_datetime(
    text: str,
    reference: datetime.datetime | None = None,
    forced_day_ref: str | None = None,
) -> datetime.datetime | None:
    """Resolve supported relative phrases to a concrete +0200 datetime.

    forced_day_ref: when set to 'today' or 'tomorrow', overrides detect_day_reference(text).
    Use the latest user message when it clearly says اليوم/el yom vs بكرا so stale keywords
    earlier in the thread do not win.
    """
    now = to_bot_tz(reference) if reference is not None else now_in_bot_tz()
    intent = detect_relative_intent(text)
    day_ref = forced_day_ref if forced_day_ref in ("today", "tomorrow") else detect_day_reference(text)

    # Extract hour from text (se3a 9, 9am, 9:00, ساعة ٩, etc.)
    hour, minute = 9, 0
    hour_match = re.search(
        r"(?:se3a|saa|ساعة|hour|at)\s*(\d{1,2})|"
        r"\b(\d{1,2})\s*(?:am|pm|صباحا|مساء|صبح|ص)?|"
        r"\b(\d{1,2}):(\d{2})",
        (text or ""),
        re.I,
    )
    if hour_match:
        g = hour_match.groups()
        h = next((x for x in (g[0], g[1], g[2]) if x is not None), None)
        m = g[3] if len(g) > 3 and g[3] is not None else 0
        if h:
            hour = min(23, max(0, int(h)))
        if m:
            minute = min(59, max(0, int(m)))
        if "pm" in (text or "").lower() or "مساء" in (text or "") or "مسا" in (text or "").lower():
            if hour < 12:
                hour += 12

    if intent == "after_two_hours":
        return (now + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)

    if intent == "tomorrow_morning":
        return (now + datetime.timedelta(days=1)).replace(hour=10, minute=0, second=0, microsecond=0)

    if intent == "later_today":
        candidate = (now + datetime.timedelta(hours=2)).replace(second=0, microsecond=0)
        if candidate.date() != now.date():
            candidate = (now + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
        return candidate

    # "today" + time (el yom se3a 9, today at 9, اليوم الساعة ٩)
    if day_ref == "today":
        today_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if today_dt <= now:
            today_dt = (now + datetime.timedelta(minutes=30)).replace(second=0, microsecond=0)
        return today_dt

    # "tomorrow" + time (bokra se3a 1, tomorrow at 3pm) — was missing; fell through and confused booking.
    if day_ref == "tomorrow":
        tomorrow_date = (now + datetime.timedelta(days=1)).date()
        tomorrow_dt = datetime.datetime.combine(
            tomorrow_date,
            datetime.time(hour=hour, minute=minute),
            tzinfo=BOT_FIXED_TZ,
        )
        return tomorrow_dt

    if not intent:
        return None

    return None


def next_future_datetime_matching_weekday(
    reference: datetime.datetime,
    target_weekday: int,
    hour: int,
    minute: int,
) -> datetime.datetime | None:
    """
    First datetime strictly after `reference` on `target_weekday` (Python weekday) with given hour/minute in same tz.
    """
    reference = to_bot_tz(reference)
    if not (0 <= target_weekday <= 6 and 0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    d0 = reference.date()
    for add in range(0, 15):
        d = d0 + datetime.timedelta(days=add)
        if d.weekday() == target_weekday:
            cand = datetime.datetime(d.year, d.month, d.day, hour, minute, 0, tzinfo=reference.tzinfo, microsecond=0)
            if cand > reference:
                return cand
    return None


def format_clinic_calendar_anchor(reference: datetime.datetime | None = None) -> str:
    """
    Single unambiguous line for the AI: English weekday + ISO date for today and tomorrow in bot TZ (+02:00).
    """
    now = to_bot_tz(reference) if reference is not None else now_in_bot_tz()
    tomorrow = now + datetime.timedelta(days=1)
    return (
        f"Today ({now.strftime('%A')}) = {now.strftime('%Y-%m-%d')}; "
        f"Tomorrow ({tomorrow.strftime('%A')}) = {tomorrow.strftime('%Y-%m-%d')} "
        f'(clinic clock, fixed UTC+02:00). For Franco: "el yom" / "lyom" / "اليوم" = Today; '
        f'"bokra" / "بكرا" = Tomorrow.'
    )


def align_datetime_to_day_reference(
    candidate: datetime.datetime, text: str, reference: datetime.datetime | None = None
) -> datetime.datetime:
    """
    Align a parsed datetime with user's day reference (today/tomorrow) when present.
    """
    now = to_bot_tz(reference) if reference is not None else now_in_bot_tz()
    dt = to_bot_tz(candidate)
    day_ref = detect_day_reference(text)
    if not day_ref:
        return dt

    if day_ref == "today" and dt.date() != now.date():
        dt = dt.replace(year=now.year, month=now.month, day=now.day)
    elif day_ref == "tomorrow":
        tomorrow = (now + datetime.timedelta(days=1)).date()
        if dt.date() != tomorrow:
            dt = dt.replace(year=tomorrow.year, month=tomorrow.month, day=tomorrow.day)

    return dt
