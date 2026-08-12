"""
Analytics Events System
Simple append-only event logging for analytics
Each event is one line in a JSONL file

Mixins: log / conversation / aggregate / format (LOC split).
"""

from __future__ import annotations

import datetime
import json
import os
from typing import Any

from services.analytics_events_aggregate import AnalyticsEventsAggregateMixin
from services.analytics_events_conversation import AnalyticsEventsConversationMixin
from services.analytics_events_format import AnalyticsEventsFormatMixin
from services.analytics_events_log import AnalyticsEventsLogMixin


class AnalyticsEvents(
    AnalyticsEventsLogMixin,
    AnalyticsEventsConversationMixin,
    AnalyticsEventsAggregateMixin,
    AnalyticsEventsFormatMixin,
):
    """Handles analytics event logging and aggregation"""

    def __init__(self) -> None:
        self.events_file = "data/analytics_events.jsonl"
        # Session rule used for Conversation 1/2/3 counting
        self.conversation_session_gap_minutes = 30
        self.openai_real_costs: dict[str, Any] | None = None
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create events file if it doesn't exist"""
        if not os.path.exists(self.events_file):
            os.makedirs(os.path.dirname(self.events_file), exist_ok=True)
            open(self.events_file, "a").close()

    def _append_event(self, event: dict[str, Any]) -> None:
        """Append a single event to the file"""
        try:
            event["timestamp"] = datetime.datetime.now().isoformat()
            with open(self.events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"❌ Error appending event: {e}")

    @staticmethod
    def _normalize_user_id(user_id: Any) -> str | None:
        """Normalize user IDs for stable deduplication."""
        if user_id is None:
            return None
        normalized = str(user_id).strip()
        if not normalized:
            return None
        normalized = normalized.replace(" ", "").replace("-", "")
        if normalized.startswith("+"):
            normalized = normalized[1:]
        return normalized

    @staticmethod
    def _is_test_user_id(user_id: str | None) -> bool:
        """Exclude known test/internal user IDs from new client metrics."""
        if not user_id:
            return True
        lower = str(user_id).lower()
        return lower in ("training", "test", "debug", "internal")

    @staticmethod
    def _parse_timestamp(timestamp: Any) -> datetime.datetime | None:
        """
        Parse supported timestamp formats into naive local datetime.
        Supports ISO values with either "T" or space separators.
        """
        if not timestamp:
            return None
        try:
            if isinstance(timestamp, datetime.datetime):
                dt = timestamp
            else:
                ts = str(timestamp).strip().replace("Z", "+00:00")
                dt = datetime.datetime.fromisoformat(ts)
            if dt.tzinfo is not None:
                return dt.astimezone().replace(tzinfo=None)
            return dt
        except Exception:
            return None


# Global instance
analytics = AnalyticsEvents()
