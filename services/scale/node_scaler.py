"""Second-layer node scale. Droplets are last resort, never a spike response."""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from services.scale.do_autoscale_guard import DigitalOceanAutoscaleForbidden, assert_droplet_autoscale_allowed
from services.scale.placement import NodeCapacity, at_safe_cap


@dataclass(frozen=True)
class NodeScaleDecision:
    action: str
    reason: str
    desired_nodes: int
    current_nodes: int


def recommend_nodes(
    *,
    nodes: list[NodeCapacity],
    assignments: dict[str, int],
    wait_p95_ms: float,
    backlog_growing: bool,
    pressure_seconds: float,
    provider_limited: bool,
    extra_quiet_seconds: float = 0.0,
    min_nodes: int = 2,
    max_nodes: int = 4,
) -> NodeScaleDecision:
    current = max(min_nodes, len([item for item in nodes if item.healthy]) or len(nodes))
    if provider_limited:
        return NodeScaleDecision("hold", "provider_limited", current, current)
    if at_safe_cap(nodes, assignments=assignments) and backlog_growing and wait_p95_ms >= 800.0:
        if pressure_seconds >= float(os.getenv("LINAS_NODE_SCALE_PRESSURE_SEC") or "90"):
            if current >= max_nodes:
                return NodeScaleDecision("hold", "node_cap_reached", current, current)
            return NodeScaleDecision("add_node", "workers_at_cap_and_sustained_pressure", current + 1, current)
    if current > min_nodes and extra_quiet_seconds >= float(os.getenv("LINAS_NODE_SCALE_QUIET_SEC") or "1800"):
        return NodeScaleDecision("drain_node", "extra_node_quiet_long_enough", current - 1, current)
    return NodeScaleDecision("hold", "in_node_worker_scale_first", current, current)


def node_create_budget_ok(
    *,
    creates_in_window: int,
    max_creates: int = 1,
    estimated_monthly_usd: float = 0.0,
    cost_cap_usd: float = 40.0,
) -> tuple[bool, str]:
    if creates_in_window >= max_creates:
        return False, "max_creates_in_window"
    if estimated_monthly_usd >= cost_cap_usd:
        return False, "cost_cap"
    return True, "ok"


def node_ready_for_capacity(*, health_ok: bool, readiness_ok: bool, redis_ok: bool, postgres_ok: bool) -> bool:
    return bool(health_ok and readiness_ok and redis_ok and postgres_ok)


def can_remove_node(
    *,
    draining_complete: bool,
    inflight_jobs: int,
    unknown_deliveries: int,
    held_locks: int,
) -> tuple[bool, str]:
    if not draining_complete:
        return False, "still_draining"
    if inflight_jobs > 0:
        return False, "inflight_jobs"
    if unknown_deliveries > 0:
        return False, "delivery_unknown"
    if held_locks > 0:
        return False, "locks_held"
    return True, "ok"


class IsolatedNodeProvider:
    """In-process stand-in for DigitalOcean droplets. Never calls the cloud API."""

    def __init__(self) -> None:
        self.nodes: list[str] = ["node-a", "node-b"]
        self.events: list[dict[str, Any]] = []

    def add_node(self) -> str:
        name = f"node-{len(self.nodes) + 1}"
        self.nodes.append(name)
        self.events.append({"kind": "add_node", "node": name, "at": time.time()})
        return name

    def drain_node(self, node_id: str) -> None:
        if node_id in self.nodes and len(self.nodes) > 1:
            self.nodes.remove(node_id)
            self.events.append({"kind": "drain_node", "node": node_id, "at": time.time()})


def try_create_droplet_locked() -> str:
    """Real DO create is gated and refuses production. Isolated tests should not call this."""
    from services.scale.leader_lock import acquire_leader

    if not acquire_leader("node-scale", ttl_seconds=30):
        raise DigitalOceanAutoscaleForbidden("node_scale_leader_not_held")
    assert_droplet_autoscale_allowed()
    from services.scale.do_autoscale_guard import create_staging_worker_droplet

    create_staging_worker_droplet()
    return "unreachable"


def apply_node_decision(
    decision: NodeScaleDecision,
    *,
    wait_p95_ms: float,
    backlog_growing: bool,
    pressure_seconds: float,
) -> dict[str, Any]:
    """Record node-layer intent. Production droplet create stays fail-closed."""
    from services.scale.autoscale_clocks import mark_node_attempt, node_attempt_cooled, store_node_need
    from services.scale.replica_controller import record_event

    payload: dict[str, Any] = {
        **asdict(decision),
        "kind": "node_layer",
        "wait_p95_ms": float(wait_p95_ms),
        "backlog_growing": bool(backlog_growing),
        "pressure_seconds": float(pressure_seconds),
        "droplet_create": "not_attempted",
        "applied": False,
    }
    if decision.action != "add_node":
        store_node_need(payload)
        record_event(payload)
        return payload
    if not node_attempt_cooled():
        payload["droplet_create"] = "cooldown"
        store_node_need(payload)
        record_event(payload)
        return payload
    mark_node_attempt()
    try:
        try_create_droplet_locked()
    except DigitalOceanAutoscaleForbidden as exc:
        payload["droplet_create"] = "refused"
        payload["refused"] = str(exc)
        store_node_need(payload)
        record_event(payload)
        return payload
    payload["droplet_create"] = "created"
    payload["applied"] = True
    store_node_need(payload)
    record_event(payload)
    return payload
