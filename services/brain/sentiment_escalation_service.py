"""Dashboard sentiment telemetry. Never keyword-escalate or skip Terra."""

from __future__ import annotations

import datetime
from typing import Any


class SentimentEscalationService:
    """Log-only sentiment stub. GPT/Terra decide handoff; no keyword owner alerts."""

    REPETITION_THRESHOLD = 3

    def __init__(self) -> None:
        self.user_message_history: dict[str, list[dict[str, Any]]] = {}
        self.escalation_reasons: dict[str, dict[str, Any]] = {}

    def analyze_sentiment(self, user_id: str, message: str, language: str = "ar") -> dict[str, Any]:
        _ = language
        if user_id not in self.user_message_history:
            self.user_message_history[user_id] = []
        self.user_message_history[user_id].append({"message": message, "timestamp": datetime.datetime.now()})
        if len(self.user_message_history[user_id]) > 10:
            self.user_message_history[user_id] = self.user_message_history[user_id][-10:]
        return {
            "sentiment": "neutral",
            "should_escalate": False,
            "escalation_reason": "",
            "confidence": 0.0,
            "escalation_score": 0,
            "detected_issues": [],
        }

    def get_escalation_info(self, user_id: str) -> dict[str, Any] | None:
        return self.escalation_reasons.get(user_id)

    def clear_user_history(self, user_id: str) -> None:
        self.user_message_history.pop(user_id, None)
        self.escalation_reasons.pop(user_id, None)


sentiment_service = SentimentEscalationService()
