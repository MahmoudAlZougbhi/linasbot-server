"""Latency-first autoscaling recommendations."""

from __future__ import annotations

from services.scale.autoscale_signal import recommend


def test_scale_up_on_small_persistent_wait() -> None:
    result = recommend(
        current_api=2,
        current_workers=2,
        queue_depth=3,
        oldest_age_seconds=1.2,
        wait_p95_ms=300.0,
        wait_p99_ms=400.0,
        ingress_per_sec=5.0,
        complete_per_sec=4.0,
    )
    assert result.action in {"scale_up", "scale_up_strong"}
    assert result.worker_replicas > 2


def test_strong_scale_up_when_backlog_accelerates() -> None:
    result = recommend(
        current_api=2,
        current_workers=4,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=8.0,
    )
    assert result.action == "scale_up_strong"
    assert result.worker_replicas >= 6


def test_no_flapping_scale_down_without_cooldown() -> None:
    result = recommend(
        current_api=3,
        current_workers=5,
        queue_depth=0,
        oldest_age_seconds=0.0,
        wait_p95_ms=10.0,
        wait_p99_ms=20.0,
        ingress_per_sec=1.0,
        complete_per_sec=1.0,
        cooldown_ok=False,
    )
    assert result.action == "hold"
    assert result.worker_replicas == 5


def test_scale_down_only_when_quiet_and_cooled() -> None:
    result = recommend(
        current_api=3,
        current_workers=5,
        queue_depth=0,
        oldest_age_seconds=0.0,
        wait_p95_ms=10.0,
        wait_p99_ms=20.0,
        ingress_per_sec=1.0,
        complete_per_sec=1.0,
        cooldown_ok=True,
    )
    assert result.action == "scale_down"
    assert result.worker_replicas == 4
    assert result.api_replicas >= 2


def test_prescale_on_ingress_ahead_of_completion() -> None:
    result = recommend(
        current_api=2,
        current_workers=2,
        queue_depth=0,
        oldest_age_seconds=0.0,
        wait_p95_ms=20.0,
        wait_p99_ms=30.0,
        ingress_per_sec=1000.0,
        complete_per_sec=700.0,
    )
    assert result.action in {"scale_up", "scale_up_strong"}
    assert result.worker_replicas > 2


def test_provider_limited_does_not_add_workers() -> None:
    result = recommend(
        current_api=2,
        current_workers=4,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=8.0,
        provider_limited=True,
    )
    assert result.action == "hold"
    assert result.worker_replicas == 4
    assert result.reason == "provider_limited_do_not_add_workers"


def test_in_node_cap_defers_to_node_layer() -> None:
    result = recommend(
        current_api=2,
        current_workers=8,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=8.0,
        in_node_worker_cap=8,
    )
    assert result.action == "hold"
    assert result.reason == "in_node_cap_need_node_layer"


def _strong(**kwargs):
    base = dict(
        current_api=2,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=4.0,
    )
    base.update(kwargs)
    return recommend(**base)


def test_strong_walks_2_4_8_16_then_extra_quiet_halves() -> None:
    workers = 2
    seen = []
    for _ in range(3):
        rec = _strong(current_workers=workers)
        assert rec.action == "scale_up_strong"
        workers = rec.worker_replicas
        seen.append(workers)
    assert seen == [4, 8, 16]
    quiet = dict(
        current_api=2,
        queue_depth=0,
        oldest_age_seconds=0.0,
        wait_p95_ms=10.0,
        wait_p99_ms=20.0,
        ingress_per_sec=1.0,
        complete_per_sec=1.0,
        cooldown_ok=True,
        extra_quiet=True,
    )
    down = []
    for _ in range(3):
        rec = recommend(current_workers=workers, **quiet)
        assert rec.action == "scale_down"
        workers = rec.worker_replicas
        down.append(workers)
    assert down == [8, 4, 2]


def test_strong_queue_pressure_does_not_add_api_replicas() -> None:
    rec = _strong(current_workers=4, current_api=2)
    assert rec.action == "scale_up_strong"
    assert rec.api_replicas == 2
    assert rec.worker_replicas >= 6
