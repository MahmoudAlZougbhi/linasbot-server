"""Replica controller plan: start when below desired, drain when above."""

from __future__ import annotations

from services.scale.replica_health import plan


def test_below_desired_starts_missing_replicas() -> None:
    result = plan(
        desired=8,
        snapshot={
            "healthy": 6,
            "counts": {"busy": 4, "ready": 2, "draining": 0, "unhealthy": 0, "dead": 1, "starting": 0},
        },
    )
    assert result.start_n == 2
    assert result.drain_n == 0
    assert result.reason == "below_desired"


def test_above_desired_drains_idle_first() -> None:
    result = plan(
        desired=4,
        snapshot={
            "healthy": 8,
            "counts": {"busy": 2, "ready": 6, "draining": 0, "unhealthy": 0, "dead": 0, "starting": 0},
        },
    )
    assert result.start_n == 0
    assert result.drain_n == 4
    assert result.reason == "above_desired"
