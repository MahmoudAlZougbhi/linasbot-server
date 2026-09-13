"""Turn published branch/hours records into searchable clock text.

CM stores opening hours on ``weekly_schedule`` (enabled/open/close/off_day).
Indexed cards and hydrate must use that SoT — string ``hours`` days are secondary.
"""

from __future__ import annotations

from typing import Any

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _day_line(day: str, row: dict[str, Any]) -> str:
    if row.get("off_day") or row.get("closed"):
        return f"{day}: closed"
    open_t = str(row.get("open") or "").strip()
    close_t = str(row.get("close") or "").strip()
    if open_t or close_t:
        note = str(row.get("note") or "").strip()
        core = f"{day}: {open_t}–{close_t}".strip("–")
        return f"{core} ({note})" if note else core
    raw = str(row.get("summary") or "").strip()
    return f"{day}: {raw}" if raw else ""


def _from_unified(schedule: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for day in _WEEKDAYS:
        row = schedule.get(day)
        if not isinstance(row, dict):
            continue
        if row.get("enabled") is False and not row.get("off_day") and not row.get("closed"):
            continue
        line = _day_line(day, row)
        if line:
            lines.append(line)
    return lines


def _from_string_hours(hours: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    summary = str(hours.get("summary") or "").strip()
    if summary:
        lines.append(summary)
    for day in _WEEKDAYS:
        value = hours.get(day)
        if isinstance(value, str) and value.strip():
            lines.append(f"{day}: {value.strip()}")
        elif isinstance(value, dict):
            line = _day_line(day, value)
            if line:
                lines.append(line)
    return lines


def schedule_lines(raw: dict[str, Any]) -> list[str]:
    """Clock lines for index + hydrate. Empty when the record has no schedule."""
    unified = raw.get("weekly_schedule")
    if isinstance(unified, dict):
        lines = _from_unified(unified)
        if lines:
            return lines
    nested = raw.get("weekly_hours") or raw.get("schedule")
    if isinstance(nested, dict):
        lines = _from_unified(nested) or _from_string_hours(nested)
        if lines:
            return lines
    hours = raw.get("hours")
    if isinstance(hours, dict):
        lines = _from_string_hours(hours) or _from_unified(hours)
        if lines:
            return lines
    # opening_hours items store days on the record itself
    direct = _from_unified(raw) or _from_string_hours(raw)
    exceptions = raw.get("exceptions") or raw.get("off_days") or []
    extra = [str(item) for item in exceptions] if isinstance(exceptions, list) else []
    return [*direct, *extra]


def schedule_search_blob(raw: dict[str, Any]) -> str:
    return " ".join(schedule_lines(raw))
