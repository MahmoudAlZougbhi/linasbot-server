"""LOC split: appointment_scheduler followups/missed under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_appointment_scheduler_modules_under_500_lines() -> None:
    assert _line_count("services/appointment_scheduler.py") < 500
    assert _line_count("services/appointment_scheduler_parse.py") < 500
    assert _line_count("services/appointment_scheduler_followups.py") < 500
    assert _line_count("services/appointment_scheduler_missed.py") < 500


def test_appointment_scheduler_preserves_public_exports() -> None:
    from services import appointment_scheduler as aps
    from services.appointment_scheduler_followups import populate_missed_yesterday_messages
    from services.appointment_scheduler_missed import populate_missed_month_messages
    from services.appointment_scheduler_parse import parse_appointment_date

    assert aps.parse_appointment_date is parse_appointment_date
    assert aps.populate_missed_yesterday_messages is populate_missed_yesterday_messages
    assert aps.populate_missed_month_messages is populate_missed_month_messages
    assert callable(aps.populate_scheduled_messages_from_appointments)
