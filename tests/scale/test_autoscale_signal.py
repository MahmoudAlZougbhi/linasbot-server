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
