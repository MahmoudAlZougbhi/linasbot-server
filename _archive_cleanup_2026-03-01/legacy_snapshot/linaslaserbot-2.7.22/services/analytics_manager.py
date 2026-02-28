# -*- coding: utf-8 -*-
"""
Analytics Manager
Provides a thin manager layer around event aggregation.
"""

from typing import Dict, Any

from services.analytics_events import analytics


class AnalyticsManager:
    """Manager for analytics aggregation operations."""

    def get_summary(self, days: int = 7) -> Dict[str, Any]:
        try:
            safe_days = max(int(days), 1)
        except (TypeError, ValueError):
            safe_days = 7
        return analytics.aggregate_analytics(days=safe_days)


analytics_manager = AnalyticsManager()
