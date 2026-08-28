"""Quiet and pressure clocks only advance while the condition holds."""

from __future__ import annotations

import fakeredis

from services.scale.autoscale_clocks import (
    extra_quiet_ready,
    node_attempt_cooled,
    pressure_seconds,
    quiet_seconds,
    set_clocks_redis_for_tests,
    store_node_need,
)


def setup_function() -> None:
    set_clocks_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))


def teardown_function() -> None:
    set_clocks_redis_for_tests(None)


def test_pressure_resets_when_load_drops() -> None:
    assert pressure_seconds(active=True, now=1000.0) == 0.0
    assert pressure_seconds(active=True, now=1090.0) == 90.0
    assert pressure_seconds(active=False, now=1091.0) == 0.0
    assert pressure_seconds(active=True, now=1092.0) == 0.0


def test_extra_quiet_requires_sustained_idle() -> None:
    assert quiet_seconds(quiet=True, now=1.0) == 0.0
    assert extra_quiet_ready(quiet_seconds(quiet=True, now=50.0)) is False
    assert extra_quiet_ready(quiet_seconds(quiet=True, now=130.0)) is True
    assert quiet_seconds(quiet=False, now=131.0) == 0.0


def test_node_attempt_cooldown_and_need_record() -> None:
    assert node_attempt_cooled(now=10.0) is True
    store_node_need({"action": "hold", "reason": "in_node_worker_scale_first"})
