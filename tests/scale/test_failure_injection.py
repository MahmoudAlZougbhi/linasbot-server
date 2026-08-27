"""Failure injection: worker death, Redis restart of session, 429 retry delay."""

from __future__ import annotations

import fakeredis

import config
from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.conversation_session import (
    hydrate_into_process,
    persist_from_process,
    set_session_redis_for_tests,
)
from services.scale.retry_backoff import retry_delay_seconds
from tests.scale.process_local import wipe_process_conversation_state


def setup_function() -> None:
    wipe_process_conversation_state()


def teardown_function() -> None:
    set_session_redis_for_tests(None)
    wipe_process_conversation_state()


def test_session_survives_client_replacement() -> None:
    first = fakeredis.FakeRedis(decode_responses=True)
    set_session_redis_for_tests(first)
    user_id = "ig:u-restart"
    hydrate_into_process(user_id)
    config.user_data_whatsapp[user_id]["current_conversation_id"] = "conv-restart"
    persist_from_process(user_id)
    dumped = first.get("linas:csess:ig:u-restart")
    assert dumped

    second = fakeredis.FakeRedis(decode_responses=True)
    second.set("linas:csess:ig:u-restart", dumped)
    set_session_redis_for_tests(second)
    wipe_process_conversation_state()
    hydrate_into_process(user_id)
    assert config.user_data_whatsapp[user_id]["current_conversation_id"] == "conv-restart"


def test_provider_429_uses_backoff() -> None:
    delay = retry_delay_seconds(attempts=2, error="http 429 rate limit redis")
    assert delay >= 5.0


def test_fail_retry_does_not_duplicate_completed_job(monkeypatch) -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = RedisQueueBackend()
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed is not None
    backend.complete(claimed)
    backend.fail(claimed, error="late_fail", retry=True)
    again = backend.claim("high_priority", worker_id="w2", timeout=1)
    assert again is None or again.status == "completed"
