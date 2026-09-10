"""Wave 3 metric reconciliation and honesty regressions."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from modules.api_security import PERMISSION_KEYS, SYSTEM_ROLE_PERMISSIONS
from services.analytics_events import AnalyticsEvents


@pytest.fixture()
def analytics_tmp(tmp_path, monkeypatch):
    events_file = tmp_path / "analytics_events.jsonl"
    events_file.write_text("", encoding="utf-8")
    a = AnalyticsEvents()
    a.events_file = str(events_file)
    return a


def _write_event(analytics: AnalyticsEvents, event: dict, hours_ago: float = 1.0):
    ts = (datetime.now() - timedelta(hours=hours_ago)).isoformat()
    event = dict(event)
    event["timestamp"] = ts
    with open(analytics.events_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


class TestMetricReconciliation:
    def test_language_counts_user_messages_only(self, analytics_tmp):
        a = analytics_tmp
        _write_event(
            a,
            {
                "type": "message",
                "source": "user",
                "msg_type": "text",
                "user_id": "u1",
                "language": "ar",
            },
        )
        _write_event(
            a,
            {
                "type": "message",
                "source": "bot",
                "msg_type": "text",
                "user_id": "u1",
                "language": "en",
            },
        )
        summary = a.aggregate_analytics(days=7)
        assert summary["success"] is True
        langs = summary["demographics"]["languages"]["counts"]
        assert langs.get("ar") == 1
        assert langs.get("en", 0) == 0
        assert summary["overview"]["total_messages"] == 2

    def test_placeholder_neutral_sentiment_not_counted(self, analytics_tmp):
        a = analytics_tmp
        _write_event(
            a,
            {
                "type": "message",
                "source": "user",
                "msg_type": "text",
                "user_id": "u1",
                "language": "ar",
                "sentiment": "neutral",
            },
        )
        _write_event(
            a,
            {
                "type": "message",
                "source": "user",
                "msg_type": "text",
                "user_id": "u2",
                "language": "ar",
                "sentiment": "positive",
            },
        )
        _write_event(
            a,
            {
                "type": "message",
                "source": "user",
                "msg_type": "text",
                "user_id": "u3",
                "language": "en",
                "sentiment": "neutral",
                "sentiment_detected": True,
            },
        )
        summary = a.aggregate_analytics(days=7)
        sentiment = summary["sentiment_distribution"]
        assert sentiment.get("positive") == 1
        assert sentiment.get("neutral") == 1
        assert sentiment.get("negative", 0) == 0

    def test_log_message_omits_default_sentiment(self, analytics_tmp):
        a = analytics_tmp
        a.log_message(source="user", msg_type="text", user_id="u1", language="ar")
        lines = Path(a.events_file).read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert "sentiment" not in payload

    def test_satisfaction_like_dislike_mapping(self, analytics_tmp):
        a = analytics_tmp
        for ft in ("good", "like", "positive"):
            _write_event(
                a,
                {
                    "type": "feedback",
                    "feedback_type": ft,
                    "user_id": "u1",
                    "reason": ft,
                },
            )
        for ft in ("wrong", "dislike", "inappropriate", "unclear"):
            _write_event(
                a,
                {
                    "type": "feedback",
                    "feedback_type": ft,
                    "user_id": "u2",
                    "reason": ft,
                },
            )
        summary = a.aggregate_analytics(days=7)
        sat = summary["satisfaction"]
        assert sat["likes"] == 3
        assert sat["dislikes"] == 4
        assert sat["total_feedback"] == 7
        # 3/7 ≈ 42.9
        assert sat["satisfaction_rate"] == 42.9

    def test_empty_period_is_legitimate_zero_not_error(self, analytics_tmp):
        a = analytics_tmp
        summary = a.aggregate_analytics(days=7)
        assert summary["success"] is True
        assert summary["overview"]["total_messages"] == 0
        assert summary["satisfaction"]["likes"] == 0
        assert summary["sentiment_distribution"] == {} or sum(summary["sentiment_distribution"].values()) == 0

    def test_aggregation_error_is_not_zero_success(self, analytics_tmp, monkeypatch):
        a = analytics_tmp

        def boom(*_args, **_kwargs):
            raise RuntimeError("disk failure")

        monkeypatch.setattr(a, "get_events", boom)
        summary = a.aggregate_analytics(days=7)
        assert summary["success"] is False
        assert "error" in summary
        assert "overview" not in summary or summary.get("overview") is None


class TestPermissionMatrixWave3:
    def test_chat_history_permission_removed(self):
        assert "chatHistory" not in PERMISSION_KEYS
        for _role, perms in SYSTEM_ROLE_PERMISSIONS.items():
            assert "chatHistory" not in perms
            assert "contentManagers" in perms
            assert "activityFlow" in perms
