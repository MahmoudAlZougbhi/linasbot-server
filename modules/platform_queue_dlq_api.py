"""Platform owner view of the Postgres dead-letter queue."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.api_security import require_platform_owner
from modules.core import app
from services.platform.feature_flags import flag_value


@app.get("/api/platform/queues/dlq")
async def list_dead_letters(request: Request) -> dict[str, Any]:
    require_platform_owner(request)
    if flag_value("queue_backend") != "pg":
        return {"success": True, "backend": "redis", "items": []}
    from services.platform.pg_jobs import PgDurableQueue

    return {"success": True, "backend": "pg", "items": PgDurableQueue().list_dlq()}


@app.post("/api/platform/queues/dlq/{job_id}/retry")
async def retry_dead_letter(job_id: str, request: Request) -> dict[str, Any]:
    require_platform_owner(request)
    if flag_value("queue_backend") != "pg":
        return {"success": False, "backend": "redis", "retried": False}
    from services.platform.pg_jobs import PgDurableQueue

    retried = PgDurableQueue().retry_dlq(job_id)
    return {"success": retried, "backend": "pg", "retried": retried}
