"""Diagnostic channel-health HTTP route. Not part of the HA verifier surface."""

from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from modules.core import app


@app.get("/api/channel-health")
async def channel_health() -> Any:
    """Per-channel PASS / WARNING / FAIL. Never a load-balancer or HA gate."""

    from services.channel_health import evaluate_channel_health

    return JSONResponse(status_code=200, content=evaluate_channel_health())
