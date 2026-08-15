"""Dashboard period windows: today, last month, last 7 days (no empty exclusive end)."""

from __future__ import annotations

from datetime import UTC, datetime

from services.tenant_mobile_dashboard.activity import build_activity_summary
from services.tenant_mobile_dashboard.periods import parse_period, parse_timezone, resolve_period_window


def _reply(ts: datetime, *, tenant_id: str = "acme") -> dict:
    return {
        "timestamp": ts.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "tenant_id": tenant_id,
        "channel": "instagram",
        "source": "qa_database",
        "bot_to_user": True,
    }


def test_parse_last_month_and_7d() -> None:
    assert parse_period("last_month") == "last_month"
    assert parse_period("7d") == "7d"
    assert parse_period("today") == "today"


def test_last_month_is_previous_local_calendar_month() -> None:
    tz = parse_timezone("Asia/Beirut")
    now = datetime(2026, 8, 15, 12, 35, tzinfo=tz)
    window = resolve_period_window(period="last_month", tz=tz, current_period_end=None, now=now)
    assert window["period"] == "last_month"
    july_start = datetime(2026, 7, 1, tzinfo=tz)
    july_end = datetime(2026, 8, 1, tzinfo=tz)
    assert window["start_ts"] == july_start.timestamp()
    assert window["end_ts"] == july_end.timestamp()

    late_july = datetime(2026, 7, 31, 23, 0, tzinfo=tz)
    early_july = datetime(2026, 7, 1, 0, 30, tzinfo=tz)
    august = datetime(2026, 8, 1, 0, 0, tzinfo=tz)
    june = datetime(2026, 6, 30, 23, 0, tzinfo=tz)
    assert window["start_ts"] <= early_july.timestamp() < window["end_ts"]
    assert window["start_ts"] <= late_july.timestamp() < window["end_ts"]
    assert not (window["start_ts"] <= august.timestamp() < window["end_ts"])
    assert not (window["start_ts"] <= june.timestamp() < window["end_ts"])

    custom = resolve_period_window(
        period="custom",
        tz=tz,
        current_period_end=None,
        now=now,
        custom_start="2026-07-01",
        custom_end="2026-07-31",
    )
    assert custom["start_ts"] == window["start_ts"]
    assert custom["end_ts"] == window["end_ts"]


def test_last_month_uses_timezone_not_utc_on_month_boundary() -> None:
    tz = parse_timezone("Asia/Beirut")
    # 1 Aug 01:00 Beirut is still 31 Jul 22:00 UTC — last month must be July, not June.
    now = datetime(2026, 8, 1, 1, 0, tzinfo=tz)
    window = resolve_period_window(period="last_month", tz=tz, current_period_end=None, now=now)
    july_start = datetime(2026, 7, 1, tzinfo=tz)
    august_start = datetime(2026, 8, 1, tzinfo=tz)
    assert window["start_ts"] == july_start.timestamp()
    assert window["end_ts"] == august_start.timestamp()


def test_last_7_days_are_seven_local_calendar_days_including_today() -> None:
    tz = parse_timezone("Asia/Beirut")
    now = datetime(2026, 8, 15, 12, 35, tzinfo=tz)
    window = resolve_period_window(period="7d", tz=tz, current_period_end=None, now=now)
    start = datetime(2026, 8, 9, tzinfo=tz)
    end = datetime(2026, 8, 16, tzinfo=tz)
    assert window["start_ts"] == start.timestamp()
    assert window["end_ts"] == end.timestamp()
    noon_today = datetime(2026, 8, 15, 12, 0, tzinfo=tz)
    early_start = datetime(2026, 8, 9, 0, 30, tzinfo=tz)
    before = datetime(2026, 8, 8, 23, 0, tzinfo=tz)
    assert window["start_ts"] <= noon_today.timestamp() < window["end_ts"]
    assert window["start_ts"] <= early_start.timestamp() < window["end_ts"]
    assert not (window["start_ts"] <= before.timestamp() < window["end_ts"])


def test_same_day_custom_is_not_an_empty_exclusive_window() -> None:
    tz = parse_timezone("Asia/Beirut")
    now = datetime(2026, 8, 15, 12, 35, tzinfo=tz)
    window = resolve_period_window(
        period="custom",
        tz=tz,
        current_period_end=None,
        now=now,
        custom_start="2026-08-15",
        custom_end="2026-08-15",
    )
    assert window["end_ts"] > window["start_ts"]
    noon = datetime(2026, 8, 15, 12, 0, tzinfo=tz)
    assert window["start_ts"] <= noon.timestamp() < window["end_ts"]


def test_last_month_activity_includes_all_july_days() -> None:
    tz = parse_timezone("Asia/Beirut")
    now = datetime(2026, 8, 15, 12, 35, tzinfo=tz)
    window = resolve_period_window(period="last_month", tz=tz, current_period_end=None, now=now)
    payload = build_activity_summary(
        "acme",
        start_ts=window["start_ts"],
        end_ts=window["end_ts"],
        integrations=[{"platform": "instagram", "connected": True}],
        entries=[
            _reply(datetime(2026, 7, 1, 0, 15, tzinfo=tz)),
            _reply(datetime(2026, 7, 15, 12, 0, tzinfo=tz)),
            _reply(datetime(2026, 7, 31, 23, 45, tzinfo=tz)),
            _reply(datetime(2026, 8, 1, 0, 15, tzinfo=tz)),
        ],
    )
    assert payload["total_activity"]["messages_replied"] == 3
    assert payload["total_activity"]["smart_answers"] == 3
