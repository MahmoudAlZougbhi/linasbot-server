"""Period + timezone validation for the tenant mobile dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DashboardPeriod = Literal["billing", "7d", "30d", "custom", "today", "last_month"]

VALID_PERIODS: frozenset[str] = frozenset({"billing", "7d", "30d", "custom", "today", "last_month"})


class PeriodValidationError(ValueError):
    code = "invalid_period"


class TimezoneValidationError(ValueError):
    code = "invalid_timezone"


def parse_period(raw: str | None) -> DashboardPeriod:
    value = (raw or "billing").strip().lower()
    if value not in VALID_PERIODS:
        raise PeriodValidationError(f"Unsupported period: {raw!r}")
    return cast(DashboardPeriod, value)


def parse_timezone(raw: str | None) -> ZoneInfo:
    name = (raw or "UTC").strip() or "UTC"
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise TimezoneValidationError(f"Unsupported timezone: {raw!r}") from exc


def _parse_custom_date(raw: str | None, *, field: str) -> date:
    text = (raw or "").strip()
    if not text:
        raise PeriodValidationError(f"Missing custom {field} date")
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise PeriodValidationError(f"Invalid custom {field} date: {raw!r}") from exc


def _local_midnight(day: date, tz: ZoneInfo) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=tz)


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Inclusive local midnight → exclusive next local midnight (calendar, not +24h)."""
    start_local = _local_midnight(day, tz)
    nxt = day + timedelta(days=1)
    return start_local, _local_midnight(nxt, tz)


def _previous_calendar_month_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    first_of_this = day.replace(day=1)
    last_of_prev = first_of_this - timedelta(days=1)
    first_of_prev = last_of_prev.replace(day=1)
    start_local, _ = _local_day_bounds(first_of_prev, tz)
    _, end_local = _local_day_bounds(last_of_prev, tz)
    return start_local, end_local


def _last_n_local_days_bounds(day: date, tz: ZoneInfo, *, days: int) -> tuple[datetime, datetime]:
    """Inclusive rolling local calendar days ending on `day` (today counts as day 1)."""
    if days < 1:
        raise PeriodValidationError("days must be >= 1")
    start_day = day - timedelta(days=days - 1)
    start_local, _ = _local_day_bounds(start_day, tz)
    _, end_local = _local_day_bounds(day, tz)
    return start_local, end_local


def resolve_period_window(
    *,
    period: DashboardPeriod,
    tz: ZoneInfo,
    current_period_end: float | None,
    now: datetime | None = None,
    custom_start: str | None = None,
    custom_end: str | None = None,
) -> dict[str, Any]:
    """Return inclusive-start exclusive-end UTC window for the selected period."""
    now_utc = now.astimezone(UTC) if now else datetime.now(UTC)
    local_now = now_utc.astimezone(tz)
    today = local_now.date()

    if period == "today":
        start_local, end_local = _local_day_bounds(today, tz)
        label = "Today"
    elif period == "last_month":
        start_local, end_local = _previous_calendar_month_bounds(today, tz)
        label = "Last month"
    elif period == "custom":
        start_day = _parse_custom_date(custom_start, field="start")
        end_day = _parse_custom_date(custom_end, field="end")
        if end_day < start_day:
            raise PeriodValidationError("Custom end date must be on or after start date")
        start_local, _ = _local_day_bounds(start_day, tz)
        _, end_local = _local_day_bounds(end_day, tz)
        if end_day > today:
            _, end_local = _local_day_bounds(today, tz)
        if end_local <= start_local:
            _, end_local = _local_day_bounds(start_day, tz)
        label = "Custom range"
    elif period == "7d":
        start_local, end_local = _last_n_local_days_bounds(today, tz, days=7)
        label = "Last 7 days"
    elif period == "30d":
        start_local = local_now - timedelta(days=30)
        end_local = local_now
        label = "Last 30 days"
    else:
        # Billing period: trailing 30 days ending at period_end (or now).
        end_ts = float(current_period_end) if current_period_end else now_utc.timestamp()
        end_utc = datetime.fromtimestamp(end_ts, tz=UTC)
        if end_utc > now_utc:
            end_utc = now_utc
        start_utc = end_utc - timedelta(days=30)
        start_local = start_utc.astimezone(tz)
        end_local = end_utc.astimezone(tz)
        label = "Current billing period"

    start_utc = start_local.astimezone(UTC)
    end_utc = end_local.astimezone(UTC)
    return {
        "period": period,
        "label": label,
        "timezone": str(tz),
        "start": start_utc.isoformat().replace("+00:00", "Z"),
        "end": end_utc.isoformat().replace("+00:00", "Z"),
        "start_ts": start_utc.timestamp(),
        "end_ts": end_utc.timestamp(),
    }


def iso_z(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(float(ts), tz=UTC).isoformat().replace("+00:00", "Z")
