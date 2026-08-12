"""LOC split: daily_template_dispatcher helpers/jobs under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.daily_template_dispatcher import DailyTemplateDispatcher, daily_template_dispatcher
from services.daily_template_dispatcher_jobs import DailyTemplateDispatcherJobsMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_daily_template_dispatcher_modules_under_500_lines() -> None:
    assert _line_count("services/daily_template_dispatcher.py") < 500
    assert _line_count("services/daily_template_dispatcher_helpers.py") < 500
    assert _line_count("services/daily_template_dispatcher_jobs.py") < 500


def test_daily_template_dispatcher_preserves_public_api() -> None:
    assert issubclass(DailyTemplateDispatcher, DailyTemplateDispatcherJobsMixin)
    assert isinstance(daily_template_dispatcher, DailyTemplateDispatcher)
    for name in ("tick", "run_template", "run_post_session_feedback_delayed"):
        assert callable(getattr(daily_template_dispatcher, name))
