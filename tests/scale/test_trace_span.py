"""Trace stages persist across webhook → worker → AI."""

from __future__ import annotations

import fakeredis

from services.scale.trace_span import mark, new_trace_id, set_trace_redis_for_tests, snapshot


def setup_function() -> None:
    set_trace_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))


def teardown_function() -> None:
    set_trace_redis_for_tests(None)


def test_trace_durations_from_stage_timestamps() -> None:
    tid = new_trace_id()
    mark(tid, "webhook_received", ts=100.0)
    mark(tid, "webhook_acked", ts=100.2)
    mark(tid, "queued", ts=100.21)
    mark(tid, "worker_started", ts=100.5)
    mark(tid, "ai_started", ts=100.6)
    mark(tid, "ai_finished", ts=103.6)
    mark(tid, "send_started", ts=103.7)
    mark(tid, "send_ok", ts=104.0)
    data = snapshot(tid)
    assert data["trace_id"] == tid
    assert abs(data["durations_ms"]["ack_ms"] - 200.0) < 1.0
    assert abs(data["durations_ms"]["queue_wait_ms"] - 290.0) < 1.0
    assert abs(data["durations_ms"]["ai_ms"] - 3000.0) < 1.0
    assert abs(data["durations_ms"]["e2e_ms"] - 4000.0) < 1.0
