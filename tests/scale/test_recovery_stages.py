"""Recovery stages A–F: crash points on a durable turn do not lose or double-send."""

from __future__ import annotations

import fakeredis

from services.ai_reply_lifecycle import begin_turn, get_turn, persist_generated_reply
from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.delivery_ledger import begin_send, confirm_sent, mark_unknown, set_delivery_redis_for_tests
from services.scale.trace_span import mark, new_trace_id, set_trace_redis_for_tests, snapshot
from services.scale.turn_pipeline import pipeline_stage
from services.scale.turn_store import set_turn_redis_for_tests


def teardown_function() -> None:
    set_turn_redis_for_tests(None)
    set_delivery_redis_for_tests(None)
    set_trace_redis_for_tests(None)


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_turn_redis_for_tests(fake)
    set_delivery_redis_for_tests(fake)
    set_trace_redis_for_tests(fake)
    return RedisQueueBackend()


def test_a_worker_dies_before_ai_job_moves(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"stage": "pre_ai"})
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w-dead", timeout=1)
    assert claimed is not None
    backend._r.delete(backend._k("lease", claimed.id))
    assert backend.reclaim_expired_leases("high_priority") == 1
    again = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert again is not None
    assert again.id == job.id


def test_c_luna_done_tera_not_started() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_trace_redis_for_tests(fake)
    tid = new_trace_id()
    mark(tid, "ai_luna_started")
    mark(tid, "ai_luna_finished")
    data = snapshot(tid)
    assert "ai_luna_finished" in data["stages"]
    assert "ai_tera_started" not in data["stages"]
    assert pipeline_stage(lifecycle_state="AI_PROCESSING") == "ai_started"


def test_d_saved_reply_is_reused_after_crash() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_turn_redis_for_tests(fake)
    set_delivery_redis_for_tests(fake)
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-d", claim_key_basis="c-d")
    persist_generated_reply(turn.logical_reply_id, reply_text="saved tera")
    loaded = get_turn(turn.logical_reply_id)
    assert loaded is not None
    assert loaded.generated_reply == "saved tera"
    assert loaded.state == "REPLY_PERSISTED"
    assert pipeline_stage(lifecycle_state=loaded.state) == "delivery_pending"


def test_e_unknown_delivery_does_not_resend() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_delivery_redis_for_tests(fake)
    key = "lr-e"
    assert begin_send(key) == "send"
    mark_unknown(key)
    assert begin_send(key) == "skip_unknown"
    assert pipeline_stage(delivery_state="unknown") == "unknown_delivery"


def test_f_sent_then_crash_reconciles_without_duplicate() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_delivery_redis_for_tests(fake)
    key = "lr-f"
    assert begin_send(key) == "send"
    confirm_sent(key, provider_message_id="mid-ok")
    assert begin_send(key) == "skip_sent"
