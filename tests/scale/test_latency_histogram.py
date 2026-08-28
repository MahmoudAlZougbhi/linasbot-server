"""Histogram percentiles are computed from Redis samples."""

from __future__ import annotations

import fakeredis

from services.scale.latency_histogram import observe, percentiles, set_histogram_redis_for_tests


def setup_function() -> None:
    set_histogram_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))


def teardown_function() -> None:
    set_histogram_redis_for_tests(None)


def test_percentiles_track_injected_samples() -> None:
    for value in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100):
        observe("job_wait_ms", float(value))
    stats = percentiles("job_wait_ms")
    assert stats["count"] == 10
    assert stats["p50"] == 50
    assert stats["max"] == 100
    assert stats["p99"] >= stats["p95"]


def test_stale_samples_outside_window_do_not_keep_p95_hot() -> None:
    observe("job_wait_ms", 9000.0, now=1.0)
    observe("job_wait_ms", 20.0, now=200.0)
    stats = percentiles("job_wait_ms", now=200.0)
    assert stats["count"] == 1
    assert stats["p95"] == 20.0
    assert stats["max"] == 20.0
