"""Period + timezone validation for the tenant mobile dashboard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DashboardPeriod = Literal["billing", "7d", "30d"]

VALID_PERIODS: frozenset[str] = frozenset({"billing", "7d", "30d"})


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


def resolve_period_window(
    *,
    period: DashboardPeriod,
    tz: ZoneInfo,
    current_period_end: float | None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return inclusive-start exclusive-end UTC window for the selected period."""
    now_utc = now.astimezone(UTC) if now else datetime.now(UTC)
    local_now = now_utc.astimezone(tz)

    if period == "7d":
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
