"""LOC split: api_integrations domain modules under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_api_integrations_modules_under_500_lines() -> None:
    assert _line_count("services/api_integrations.py") < 500
    assert _line_count("services/api_integrations_http.py") < 500
    assert _line_count("services/api_integrations_catalog.py") < 500
    assert _line_count("services/api_integrations_reminders.py") < 500
    assert _line_count("services/api_integrations_status.py") < 500
    assert _line_count("services/api_integrations_booking.py") < 500
    assert _line_count("services/api_integrations_edit.py") < 500
    assert _line_count("services/api_integrations_customers.py") < 500


def test_api_integrations_preserves_public_api() -> None:
    from services import api_integrations as api_mod
    from services.api_integrations_http import log_report_event as http_log_report_event

    assert api_mod.log_report_event is http_log_report_event
    for name in (
        "get_customer_by_phone",
        "get_customer_appointments",
        "send_appointment_reminders",
        "check_customer_gender",
        "create_customer",
        "get_paused_appointments_between_dates",
        "generate_daily_report_command",
        "get_missed_appointments",
        "check_next_appointment",
    ):
        assert callable(getattr(api_mod, name))
