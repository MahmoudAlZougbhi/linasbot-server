"""
Analytics Manager
Provides a thin manager layer around event aggregation.
"""

from __future__ import annotations

from typing import Any

from services.analytics_events import analytics


class AnalyticsManager:
    """Manager for analytics aggregation operations."""

    def get_summary(self, days: int = 7) -> Any:
        try:
            safe_days = max(int(days), 1)
        except (TypeError, ValueError):
            safe_days = 7
        return analytics.aggregate_analytics(days=safe_days)


analytics_manager = AnalyticsManager()
