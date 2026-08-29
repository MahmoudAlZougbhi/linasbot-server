"""Leader-only autoscale tick: in-node first, node layer fail-closed."""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable
from typing import Any


def _in_node_worker_cap() -> int:
    from services.scale.worker_slots import cluster_in_node_worker_cap

    return cluster_in_node_worker_cap()


def _quiet_signals(
    *, queue_depth: int, oldest_age_seconds: float, wait_p95_ms: float, ingress: float, complete: float
) -> bool:
    p95_down = float(os.getenv("LINAS_AUTOSCALE_WAIT_P95_DOWN_MS") or "50")
    return (
        wait_p95_ms <= p95_down
        and int(queue_depth) == 0
        and float(oldest_age_seconds) < 0.2
        and float(ingress) <= float(complete) + 0.1
    )


def _ha_pair(current_workers: int) -> tuple[list[Any], dict[str, int]]:
    from services.scale.placement import NodeCapacity, place_workers
    from services.scale.worker_slots import per_node_high_cap

    cap = per_node_high_cap()
    nodes = [
        NodeCapacity("ha-a", True, 0.0, 0.0, cap),
        NodeCapacity("ha-b", True, 0.0, 0.0, cap),
    ]
    return nodes, place_workers(int(current_workers), nodes)


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
    from services.scale.autoscale_clocks import extra_quiet_ready, pressure_seconds, quiet_seconds
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
    from services.scale.rate_window import snapshot_rates

    ingress, complete = snapshot_rates()
    queue_depth = int(depths.get("high_priority") or 0) + int(depths.get("background") or 0)
    oldest_age = max([float(oldest.get(name) or 0.0) for name in oldest] or [0.0])
    wait_p95 = float(wait.get("p95") or 0.0)
    now = time.time()
    cap = _in_node_worker_cap()
    quiet = _quiet_signals(
        queue_depth=queue_depth,
        oldest_age_seconds=oldest_age,
        wait_p95_ms=wait_p95,
        ingress=ingress,
        complete=complete,
    )
    qsec = quiet_seconds(quiet=quiet, now=now)
    node_capped = cap > 0 and int(state.workers) >= cap
    psec = pressure_seconds(active=bool(node_capped and not quiet), now=now)
    result = tick(
        current_api=int(state.api),
        current_workers=int(state.workers),
        queue_depth=queue_depth,
        oldest_age_seconds=oldest_age,
        wait_p95_ms=wait_p95,
        wait_p99_ms=float(wait.get("p99") or 0.0),
        ingress_per_sec=ingress,
        complete_per_sec=complete,
        cooldown_ok=now >= float(state.cooldown_until),
        in_node_worker_cap=cap,
        extra_quiet=extra_quiet_ready(qsec),
    )
    rec = result.get("recommendation") or {}
    if rec.get("reason") != "in_node_cap_need_node_layer":
        return
    from services.scale.node_scaler import apply_node_decision, recommend_nodes

    nodes, placed = _ha_pair(int(state.workers))
    decision = recommend_nodes(
        nodes=nodes,
        assignments=placed,
        wait_p95_ms=wait_p95,
        backlog_growing=ingress > complete + 0.5,
        pressure_seconds=psec,
        provider_limited=False,
        extra_quiet_seconds=qsec,
    )
    apply_node_decision(
        decision,
        wait_p95_ms=wait_p95,
        backlog_growing=ingress > complete + 0.5,
        pressure_seconds=psec,
    )
