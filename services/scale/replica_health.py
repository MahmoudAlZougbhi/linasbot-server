"""Reconcile desired replicas against the worker registry snapshot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReplicaPlan:
    desired: int
    healthy: int
    busy: int
    draining: int
    unhealthy: int
    dead: int
    starting: int
    start_n: int
    drain_n: int
    reason: str


def plan(*, desired: int, snapshot: dict[str, Any]) -> ReplicaPlan:
    counts = dict(snapshot.get("counts") or {})
    healthy = int(snapshot.get("healthy") or 0)
    busy = int(counts.get("busy") or 0)
    draining = int(counts.get("draining") or 0)
    unhealthy = int(counts.get("unhealthy") or 0)
    dead = int(counts.get("dead") or 0)
    starting = int(counts.get("starting") or 0)
    want = max(0, int(desired))
    if healthy < want:
        return ReplicaPlan(
            desired=want,
            healthy=healthy,
            busy=busy,
            draining=draining,
            unhealthy=unhealthy,
            dead=dead,
            starting=starting,
            start_n=want - healthy,
            drain_n=0,
            reason="below_desired",
        )
    if healthy > want:
        idle = max(0, healthy - busy - starting)
        drain_n = min(healthy - want, idle if idle else healthy - want)
        return ReplicaPlan(
            desired=want,
            healthy=healthy,
            busy=busy,
            draining=draining,
            unhealthy=unhealthy,
            dead=dead,
            starting=starting,
            start_n=0,
            drain_n=drain_n,
            reason="above_desired",
        )
    return ReplicaPlan(
        desired=want,
        healthy=healthy,
        busy=busy,
        draining=draining,
        unhealthy=unhealthy,
        dead=dead,
        starting=starting,
        start_n=0,
        drain_n=0,
        reason="matched",
    )
