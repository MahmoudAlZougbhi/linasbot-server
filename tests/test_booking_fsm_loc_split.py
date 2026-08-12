"""LOC split: booking_fsm detect/merge under 500 lines."""

from __future__ import annotations

from pathlib import Path


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_booking_fsm_modules_under_500_lines() -> None:
    assert _line_count("services/booking/booking_fsm.py") < 500
    assert _line_count("services/booking/booking_fsm_detect.py") < 500
    assert _line_count("services/booking/booking_fsm_merge.py") < 500


def test_booking_fsm_preserves_public_exports() -> None:
    from services.booking import booking_fsm as fsm
    from services.booking.booking_fsm_detect import fsm_enabled, new_fsm_state
    from services.booking.booking_fsm_merge import can_execute_submit, merge_patch

    assert fsm.fsm_enabled is fsm_enabled
    assert fsm.new_fsm_state is new_fsm_state
    assert fsm.merge_patch is merge_patch
    assert fsm.can_execute_submit is can_execute_submit
    assert callable(fsm.build_prompt_block)
    assert callable(fsm.mark_booking_completed)
