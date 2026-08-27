"""Structured DLQ records keep replay delivery-only."""

from __future__ import annotations

import fakeredis

from services.omnichannel.dlq import replay_delivery_only
from services.scale.dlq_record import classify_error, record_dead, set_dlq_redis_for_tests


def setup_function() -> None:
    set_dlq_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))


def teardown_function() -> None:
    set_dlq_redis_for_tests(None)


def test_429_is_transient_and_500_is_transient() -> None:
    assert classify_error("HTTP 429 rate limit") == "transient"
    assert classify_error("provider 500") == "transient"
    assert classify_error("PermanentJobError: unknown_job_type") == "permanent"


def test_record_includes_required_fields() -> None:
    rec = record_dead(
        job_id="j1",
        job_type="combine_flush",
        tenant_id="clinic1",
        error="timeout talking to openai",
        attempts=5,
        conversation_key="clinic1:instagram:u1",
        channel="instagram",
        created_at=1.0,
        attempt_times=[1.0, 2.0, 4.0],
    )
    assert rec["tenant_id"] == "clinic1"
    assert rec["channel"] == "instagram"
    assert rec["error_kind"] == "transient"
    assert rec["replay_mode"] == "delivery_only"
    assert rec["attempts"] == 5


def test_replay_forbids_ai_regeneration() -> None:
    assert replay_delivery_only({"mode": "delivery_only"})["ok"] is True
    try:
        replay_delivery_only({"mode": "delivery_only", "regenerate_ai": True})
        raise AssertionError("expected PermissionError")
    except PermissionError:
        pass
