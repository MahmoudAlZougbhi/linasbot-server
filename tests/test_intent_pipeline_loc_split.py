"""LOC split: booking intent_pipeline helpers/crm/resolve under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_intent_pipeline_modules_under_500_lines() -> None:
    assert _line_count("services/booking/intent_pipeline.py") < 500
    assert _line_count("services/booking/intent_pipeline_helpers.py") < 500
    assert _line_count("services/booking/intent_pipeline_crm.py") < 500
    assert _line_count("services/booking/intent_pipeline_resolve.py") < 500


def test_intent_pipeline_preserves_public_exports() -> None:
    from services.booking import intent_pipeline as ip
    from services.booking.intent_pipeline_crm import (
        finalize_crm_booking_tool_output,
        legacy_create_appointment_tool_output,
    )
    from services.booking.constants import _service_requires_machine

    assert callable(ip.handle_submit_booking_intent)
    assert ip.finalize_crm_booking_tool_output is finalize_crm_booking_tool_output
    assert ip.legacy_create_appointment_tool_output is legacy_create_appointment_tool_output
    assert ip._service_requires_machine is _service_requires_machine
