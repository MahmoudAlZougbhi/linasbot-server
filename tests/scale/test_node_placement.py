"""Place workers across nodes; scale nodes only after in-node cap + sustained pressure."""

from __future__ import annotations

import fakeredis

from services.scale.leader_lock import acquire_leader, release_leader, set_leader_redis_for_tests
from services.scale.node_scaler import IsolatedNodeProvider, recommend_nodes
from services.scale.placement import NodeCapacity, at_safe_cap, place_workers


def test_two_healthy_nodes_split_eight_workers() -> None:
    nodes = [
        NodeCapacity("node-a", True, cpu_pct=20, mem_pct=30, worker_cap=16),
        NodeCapacity("node-b", True, cpu_pct=25, mem_pct=30, worker_cap=16),
    ]
    placed = place_workers(8, nodes)
    assert placed["node-a"] + placed["node-b"] == 8
    assert placed["node-a"] == 4
    assert placed["node-b"] == 4


def test_dead_node_is_absorbed_up_to_remaining_cap() -> None:
    nodes = [
        NodeCapacity("node-a", False, cpu_pct=0, mem_pct=0, worker_cap=16),
        NodeCapacity("node-b", True, cpu_pct=40, mem_pct=40, worker_cap=16),
    ]
    placed = place_workers(8, nodes)
    assert placed["node-a"] == 0
    assert placed["node-b"] == 8


def test_small_spike_does_not_add_a_droplet() -> None:
    nodes = [
        NodeCapacity("node-a", True, cpu_pct=30, mem_pct=30, worker_cap=16, current_workers=4),
        NodeCapacity("node-b", True, cpu_pct=30, mem_pct=30, worker_cap=16, current_workers=4),
    ]
    placed = place_workers(8, nodes)
    decision = recommend_nodes(
        nodes=nodes,
        assignments=placed,
        wait_p95_ms=300.0,
        backlog_growing=True,
        pressure_seconds=10.0,
        provider_limited=False,
    )
    assert decision.action == "hold"
    assert decision.reason == "in_node_worker_scale_first"


def test_add_node_only_at_cap_with_sustained_pressure() -> None:
    nodes = [
        NodeCapacity("node-a", True, cpu_pct=80, mem_pct=70, worker_cap=8, current_workers=8),
        NodeCapacity("node-b", True, cpu_pct=80, mem_pct=70, worker_cap=8, current_workers=8),
    ]
    placed = {"node-a": 8, "node-b": 8}
    assert at_safe_cap(nodes, assignments=placed)
    decision = recommend_nodes(
        nodes=nodes,
        assignments=placed,
        wait_p95_ms=900.0,
        backlog_growing=True,
        pressure_seconds=120.0,
        provider_limited=False,
        max_nodes=4,
    )
    assert decision.action == "add_node"
    provider = IsolatedNodeProvider()
    provider.add_node()
    assert len(provider.nodes) == 3
    assert provider.events[-1]["kind"] == "add_node"


def test_leader_lock_is_exclusive() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_leader_redis_for_tests(fake)
    assert acquire_leader("node-scale", ttl_seconds=15) is True
    assert acquire_leader("node-scale", ttl_seconds=15) is False
    release_leader("node-scale")
    set_leader_redis_for_tests(None)


def test_node_budget_and_drain_gates() -> None:
    from services.scale.node_scaler import can_remove_node, node_create_budget_ok, node_ready_for_capacity

    ok, reason = node_create_budget_ok(
        creates_in_window=0, max_creates=1, estimated_monthly_usd=18.0, cost_cap_usd=40.0
    )
    assert ok is True
    blocked, why = node_create_budget_ok(creates_in_window=1, max_creates=1)
    assert blocked is False
    assert why == "max_creates_in_window"
    assert node_ready_for_capacity(health_ok=True, readiness_ok=True, redis_ok=True, postgres_ok=True) is True
    assert node_ready_for_capacity(health_ok=True, readiness_ok=False, redis_ok=True, postgres_ok=True) is False
    allowed, gate = can_remove_node(draining_complete=True, inflight_jobs=0, unknown_deliveries=0, held_locks=0)
    assert allowed is True
    denied, gate = can_remove_node(draining_complete=True, inflight_jobs=0, unknown_deliveries=1, held_locks=0)
    assert denied is False
    assert gate == "delivery_unknown"


def test_dead_node_triggers_add_only_when_remaining_cap_is_exhausted() -> None:
    nodes = [
        NodeCapacity("node-a", False, cpu_pct=0, mem_pct=0, worker_cap=16),
        NodeCapacity("node-b", True, cpu_pct=90, mem_pct=80, worker_cap=8, current_workers=8),
    ]
    placed = place_workers(16, nodes)
    assert placed["node-b"] == 8
    assert placed["node-a"] == 0
    decision = recommend_nodes(
        nodes=nodes,
        assignments=placed,
        wait_p95_ms=900.0,
        backlog_growing=True,
        pressure_seconds=120.0,
        provider_limited=False,
        max_nodes=4,
        min_nodes=1,
    )
    assert decision.action == "add_node"
