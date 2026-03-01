# -*- coding: utf-8 -*-
"""
Activity Flow API - Serves User ↔ Bot ↔ AI interaction logs for dashboard transparency.
"""

from modules.core import app
from services.interaction_flow_logger import get_recent_flows


@app.get("/api/flow/logs")
async def get_flow_logs(limit: int = 50):
    """
    Get recent interaction flow entries for the Activity Flow dashboard.
    Shows: User message → Bot → AI → Bot → User
    """
    logs = get_recent_flows(limit=min(limit, 100))
    return {"success": True, "data": logs, "count": len(logs)}
