"""Period + timezone validation for the tenant mobile dashboard."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DashboardPeriod = Literal["billing", "7d", "30d", "custom", "today"]

VALID_PERIODS: frozenset[str] = frozenset({"billing", "7d", "30d", "custom", "today"})


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


def _local_day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Inclusive local midnight → exclusive next local midnight."""
    start_local = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start_local, start_local + timedelta(days=1)


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

    if period == "today":
        start_local, end_local = _local_day_bounds(local_now.date(), tz)
        label = "Today"
    elif period == "custom":
        start_day = _parse_custom_date(custom_start, field="start")
        end_day = _parse_custom_date(custom_end, field="end")
        if end_day < start_day:
            raise PeriodValidationError("Custom end date must be on or after start date")
        start_local, _ = _local_day_bounds(start_day, tz)
        _, end_local = _local_day_bounds(end_day, tz)
        # Never emit a zero-width or inverted window (same-day Today used to collapse).
        if end_local <= start_local:
            end_local = start_local + timedelta(days=1)
        if end_local > local_now + timedelta(days=1) and start_local < local_now:
            end_local = local_now
        if end_local <= start_local:
            end_local = start_local + timedelta(days=1)
        label = "Custom range"
    elif period == "7d":
        start_local = local_now - timedelta(days=7)
        end_local = local_now
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
