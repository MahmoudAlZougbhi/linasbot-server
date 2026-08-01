"""
Activity Flow API - Serves User ↔ Bot ↔ AI interaction logs for dashboard transparency.
"""

from __future__ import annotations

import asyncio
from typing import Any

from modules.core import app
from services.interaction_flow_logger import get_recent_flows


@app.get("/api/flow/logs")
async def get_flow_logs(limit: int = 50, search: str | None = None) -> Any:
    """
    Get recent interaction flow entries for the Activity Flow dashboard.
    Shows: User message → Bot → AI → Bot → User
    search: Filter by phone number (partial match)
    """
    # Run in thread pool so file read / JSON parse don't block the event loop
    logs = await asyncio.to_thread(get_recent_flows, limit=min(limit, 100), search_phone=search)
    return {"success": True, "data": logs, "count": len(logs)}
