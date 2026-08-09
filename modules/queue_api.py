"""Queue health / readiness for workers."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.api_security import require_session
from modules.core import app
from services.job_queue import job_queue
from services.queues.config import redis_required, redis_url


@app.get("/api/queue/health")
async def queue_health(request: Request) -> Any:
    """Authenticated health; platform_owner sees full heartbeat detail."""
    session = require_session(request)
    health = job_queue.health()
    if session.role != "platform_owner":
        health = {
            "ok": health.get("ok"),
            "backend": health.get("backend"),
            "production_ready": health.get("production_ready"),
        }
    return {"success": True, "queue": health, "redis_configured": bool(redis_url())}


@app.get("/api/queue/ready")
async def queue_ready() -> Any:
    """Public-ish readiness used by deploy checks (no secrets)."""
    health = job_queue.health()
    required = redis_required()
    ok = bool(health.get("ok")) and (health.get("production_ready") if required else True)
    return {
        "ok": ok,
        "role": "queue_readiness",
        "backend": health.get("backend"),
        "production_ready": health.get("production_ready"),
        "redis_required": required,
        "redis_configured": bool(redis_url()),
    }
