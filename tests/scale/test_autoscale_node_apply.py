"""Node-layer add_node is recorded; DigitalOcean create stays fail-closed."""

from __future__ import annotations

import fakeredis

from services.scale.autoscale_clocks import set_clocks_redis_for_tests
from services.scale.leader_lock import set_leader_redis_for_tests
from services.scale.node_scaler import apply_node_decision, recommend_nodes
from services.scale.placement import NodeCapacity, at_safe_cap
from services.scale.replica_controller import set_controller_redis_for_tests


def setup_function() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_clocks_redis_for_tests(fake)
    set_controller_redis_for_tests(fake)
    set_leader_redis_for_tests(fake)


def teardown_function() -> None:
    set_clocks_redis_for_tests(None)
    set_controller_redis_for_tests(None)
    set_leader_redis_for_tests(None)


def test_add_node_intent_is_refused_without_staging_gates(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_AUTOSCALE_DO_STAGING", raising=False)
    monkeypatch.delenv("LINAS_OMNI_CERT_STAGING", raising=False)
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
    result = apply_node_decision(
        decision,
        wait_p95_ms=900.0,
        backlog_growing=True,
        pressure_seconds=120.0,
    )
    assert result["droplet_create"] == "refused"
    assert result["applied"] is False
    assert "LINAS_AUTOSCALE_DO_STAGING" in str(result.get("refused") or "")


def test_short_pressure_does_not_attempt_a_droplet() -> None:
    nodes = [
        NodeCapacity("node-a", True, cpu_pct=30, mem_pct=30, worker_cap=16, current_workers=4),
        NodeCapacity("node-b", True, cpu_pct=30, mem_pct=30, worker_cap=16, current_workers=4),
    ]
    decision = recommend_nodes(
        nodes=nodes,
        assignments={"node-a": 4, "node-b": 4},
        wait_p95_ms=300.0,
        backlog_growing=True,
        pressure_seconds=10.0,
        provider_limited=False,
    )
    assert decision.action == "hold"
    result = apply_node_decision(
        decision,
        wait_p95_ms=300.0,
        backlog_growing=True,
        pressure_seconds=10.0,
    )
    assert result["droplet_create"] == "not_attempted"
    assert result["action"] == "hold"
