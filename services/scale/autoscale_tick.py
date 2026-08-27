"""Leader-only autoscale tick: recommend then write desired replica counts."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable


async def run_autoscale_tick(stopping: Callable[[], bool]) -> None:
    while not stopping():
        await asyncio.sleep(5)
        try:
            _tick_once()
        except Exception:
            continue


def _tick_once() -> None:
    from services.scale.leader_lock import acquire_leader
    from services.scale.replica_controller import apply_enabled, tick

    if not apply_enabled():
        return
    if not acquire_leader("autoscale-tick", ttl_seconds=12):
        return
    from services.job_queue import job_queue
    from services.scale.latency_histogram import snapshot as hist_snapshot
    from services.scale.replica_controller import current_replicas

    depths = {}
    oldest = {}
    try:
        depths = job_queue.depth() or {}
        backend = getattr(job_queue, "_redis", None)
        if backend is not None and hasattr(backend, "oldest_age_seconds"):
            oldest = {
                name: backend.oldest_age_seconds(name)
                for name in ("high_priority", "interactive", "background", "expensive")
            }
    except Exception:
        return
    wait = (hist_snapshot() or {}).get("job_wait_ms") or {}
    state = current_replicas()
    tick(
        current_api=int(state.api),
        current_workers=int(state.workers),
        queue_depth=int(depths.get("high_priority") or 0) + int(depths.get("background") or 0),
        oldest_age_seconds=max([float(oldest.get(name) or 0.0) for name in oldest] or [0.0]),
        wait_p95_ms=float(wait.get("p95") or 0.0),
        wait_p99_ms=float(wait.get("p99") or 0.0),
        ingress_per_sec=0.0,
        complete_per_sec=0.0,
        cooldown_ok=True,
        in_node_worker_cap=int(os.getenv("LINAS_QUEUE_CONCURRENCY_CAP_HIGH") or "8") * 2,
    )
