# -*- coding: utf-8 -*-
"""
Analytics Service
Orchestrates analytics aggregation and optional real OpenAI usage costs.
"""

from typing import Any, Dict

from services.analytics_manager import analytics_manager
from services.openai_usage_service import openai_usage_service


class AnalyticsService:
    """Service layer for analytics API consumers."""

    @staticmethod
    def _safe_days(value: Any, default: int = 7) -> int:
        try:
            return max(int(value), 1)
        except (TypeError, ValueError):
            return default

    async def get_analytics_summary(self, time_range: int = 7, use_real_costs: bool = True) -> Dict[str, Any]:
        safe_days = self._safe_days(time_range, default=7)
        result = analytics_manager.get_summary(days=safe_days)

        if not result.get("success"):
            return result

        token_usage = result.setdefault("token_usage", {})
        token_usage["source"] = "estimated"

        if not use_real_costs:
            return result

        try:
            openai_usage = await openai_usage_service.get_usage_for_last_n_days(safe_days)
            if openai_usage.get("success"):
                token_usage["total_cost_usd"] = openai_usage.get("total_cost_usd", token_usage.get("total_cost_usd", 0))
                token_usage["total_tokens"] = openai_usage.get("total_tokens", token_usage.get("total_tokens", 0))
                token_usage["model_breakdown"] = openai_usage.get("model_breakdown", token_usage.get("model_breakdown", {}))
                token_usage["daily_costs"] = openai_usage.get("daily_costs", [])
                token_usage["source"] = "openai_api"
        except Exception as e:
            print(f"⚠️ AnalyticsService: failed to fetch real OpenAI costs: {e}")

        return result


analytics_service = AnalyticsService()
