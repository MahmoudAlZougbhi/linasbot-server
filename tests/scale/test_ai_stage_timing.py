"""Luna/Tera stage timers record histogram samples without changing models."""

from __future__ import annotations

import asyncio

import fakeredis
import pytest

from services.scale.ai_stage_timing import record_gap_ms, time_stage
from services.scale.latency_histogram import percentiles, set_histogram_redis_for_tests
from services.scale.trace_context import set_trace_id
from services.scale.trace_span import mark, new_trace_id, set_trace_redis_for_tests, snapshot


def setup_function() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_histogram_redis_for_tests(fake)
    set_trace_redis_for_tests(fake)


def teardown_function() -> None:
    set_histogram_redis_for_tests(None)
    set_trace_redis_for_tests(None)
    set_trace_id("")


@pytest.mark.asyncio
async def test_luna_tera_gap_is_recorded() -> None:
    tid = new_trace_id()
    set_trace_id(tid)
    async with time_stage("luna"):
        await asyncio.sleep(0.01)
    record_gap_ms("luna", "tera", 2.5)
    async with time_stage("tera"):
        await asyncio.sleep(0.01)
    luna = percentiles("ai_luna_ms")
    tera = percentiles("ai_tera_ms")
    gap = percentiles("ai_luna_tera_gap_ms")
    assert luna["count"] >= 1
    assert tera["count"] >= 1
    assert gap["p50"] == 2.5
    data = snapshot(tid)
    assert "luna_ms" in data["durations_ms"]
    assert "tera_ms" in data["durations_ms"]


def test_trace_splits_post_ai_and_send() -> None:
    tid = new_trace_id()
    mark(tid, "ai_finished", ts=10.0)
    mark(tid, "send_started", ts=10.2)
    mark(tid, "send_ok", ts=10.5)
    data = snapshot(tid)
    assert abs(data["durations_ms"]["post_ai_ms"] - 200.0) < 1.0
    assert abs(data["durations_ms"]["send_ms"] - 300.0) < 1.0
