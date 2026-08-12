"""Scale metrics + role readiness HTTP surface (LOC-split from dashboard health)."""

from __future__ import annotations

from typing import Any

from modules.core import app


@app.get("/api/scale/metrics")
async def scale_metrics() -> Any:
    """Safe operational counters (no PII / secrets / message bodies)."""
    from services.scale import metrics as scale_metrics_mod
    from services.scale.shutdown import shutdown_coordinator

    payload = scale_metrics_mod.snapshot()
    payload["drain"] = shutdown_coordinator.snapshot()
    try:
        from services.job_queue import job_queue

        payload["queue_depth"] = job_queue.depth()
    except Exception as exc:
        payload["queue_depth_error"] = type(exc).__name__
    return payload


@app.get("/api/scale/ready")
async def scale_ready() -> Any:
    """Role-aware readiness (LINAS_SERVICE_ROLE)."""
    from fastapi.responses import JSONResponse

    from services.scale.readiness_roles import readiness_for_role

    payload = readiness_for_role()
    return JSONResponse(status_code=200 if payload.get("ok") else 503, content=payload)
