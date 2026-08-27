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
        from services.omnichannel import metrics as omni_metrics

        payload["omnichannel"] = omni_metrics.snapshot()
    except Exception as exc:
        payload["omnichannel_error"] = type(exc).__name__
    try:
        from services.job_queue import job_queue

        payload["queue_depth"] = job_queue.depth()
        backend = getattr(job_queue, "_redis", None)
        if backend is not None and hasattr(backend, "oldest_age_seconds"):
            payload["oldest_age_seconds"] = {
                name: backend.oldest_age_seconds(name)
                for name in ("high_priority", "interactive", "background", "expensive")
            }
    except Exception as exc:
        payload["queue_depth_error"] = type(exc).__name__
    try:
        from services.scale.latency_histogram import snapshot as hist_snapshot

        payload["latency"] = hist_snapshot()
    except Exception as exc:
        payload["latency_error"] = type(exc).__name__
    try:
        from services.scale.autoscale_signal import recommendation_dict
        from services.scale.replica_controller import current_replicas, recent_events

        replica_state = current_replicas()
        depths = payload.get("queue_depth") or {}
        oldest = payload.get("oldest_age_seconds") or {}
        wait = (payload.get("latency") or {}).get("job_wait_ms") or {}
        from services.scale.rate_window import snapshot_rates

        ingress, complete = snapshot_rates()
        payload["autoscale"] = recommendation_dict(
            current_api=int(replica_state.api),
            current_workers=int(replica_state.workers),
            queue_depth=int(depths.get("high_priority") or 0) + int(depths.get("background") or 0),
            oldest_age_seconds=max(
                [float(oldest.get(name) or 0.0) for name in ("high_priority", "background", "interactive", "expensive")]
                or [0.0]
            ),
            wait_p95_ms=float(wait.get("p95") or 0.0),
            wait_p99_ms=float(wait.get("p99") or 0.0),
            ingress_per_sec=ingress,
            complete_per_sec=complete,
            cooldown_ok=True,
        )
        payload["replicas"] = {
            "api": replica_state.api,
            "workers": replica_state.workers,
            "draining_workers": replica_state.draining_workers,
            "last_action": replica_state.last_action,
        }
        payload["autoscale_events"] = recent_events(limit=10)
    except Exception as exc:
        payload["autoscale_error"] = type(exc).__name__
    try:
        from services.scale.dlq_record import recent

        payload["dlq_recent"] = recent(limit=20)
    except Exception as exc:
        payload["dlq_error"] = type(exc).__name__
    return payload


@app.get("/api/scale/ready")
async def scale_ready() -> Any:
    """Role-aware readiness (LINAS_SERVICE_ROLE)."""
    from fastapi.responses import JSONResponse

    from services.scale.readiness_roles import readiness_for_role

    payload = readiness_for_role()
    return JSONResponse(status_code=200 if payload.get("ok") else 503, content=payload)
