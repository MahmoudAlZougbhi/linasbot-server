"""LOC split: analytics_events log/conversation/aggregate/format under 500 lines."""

from __future__ import annotations

from pathlib import Path

from services.analytics_events import AnalyticsEvents, analytics
from services.analytics_events_aggregate import AnalyticsEventsAggregateMixin
from services.analytics_events_conversation import AnalyticsEventsConversationMixin
from services.analytics_events_format import AnalyticsEventsFormatMixin
from services.analytics_events_log import AnalyticsEventsLogMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_analytics_events_modules_under_500_lines() -> None:
    assert _line_count("services/analytics_events.py") < 500
    assert _line_count("services/analytics_events_log.py") < 500
    assert _line_count("services/analytics_events_conversation.py") < 500
    assert _line_count("services/analytics_events_aggregate.py") < 500
    assert _line_count("services/analytics_events_format.py") < 500


def test_analytics_events_preserves_public_api_via_mixins() -> None:
    assert issubclass(AnalyticsEvents, AnalyticsEventsLogMixin)
    assert issubclass(AnalyticsEvents, AnalyticsEventsConversationMixin)
    assert issubclass(AnalyticsEvents, AnalyticsEventsAggregateMixin)
    assert issubclass(AnalyticsEvents, AnalyticsEventsFormatMixin)
    assert isinstance(analytics, AnalyticsEvents)
    for name in (
        "log_message",
        "log_appointment",
        "get_events",
        "aggregate_analytics",
        "_format_analytics_response",
        "_build_conversation_type_metrics",
    ):
        assert callable(getattr(AnalyticsEvents, name))
