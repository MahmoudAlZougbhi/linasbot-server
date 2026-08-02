"""
Analytics API Module
Uses event-based analytics with append-only JSONL file
"""

from __future__ import annotations

from typing import Any

from modules.core import app
from services.analytics_service import analytics_service


@app.get("/api/analytics/summary")
async def get_analytics_summary(time_range: int = 7, use_real_costs: bool = True) -> Any:
    """
    Get comprehensive analytics summary

    Args:
        time_range: Number of days to include (default: 7)
        use_real_costs: Whether to fetch real costs from OpenAI API (default: True)

    Returns:
        JSON with all analytics data aggregated from events
    """
    try:
        print(f"📊 Analytics API: Aggregating events for last {time_range} days")
        result = await analytics_service.get_analytics_summary(
            time_range=time_range,
            use_real_costs=use_real_costs,
        )

        if result.get("success"):
            print("✅ Analytics API: Successfully aggregated analytics")
            return {"success": True, "data": result}
        else:
            print("⚠️ Analytics API: Error aggregating data")
            return {"success": False, "error": result.get("error", "Unknown error"), "data": result}

    except Exception as e:
        print(f"❌ Analytics API Error: {e}")
        import traceback

        traceback.print_exc()
        return {"success": False, "error": str(e)}
