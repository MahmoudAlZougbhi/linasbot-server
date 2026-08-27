"""Combine flush jobs bump due time instead of duplicating work."""

from __future__ import annotations

import time

import fakeredis

from services.queues.models import QueueJob
from services.scale.message_combine_schedule import schedule_combine_flush


def test_second_schedule_bumps_existing_job(monkeypatch) -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb
    from services import job_queue as jq

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = rb.RedisQueueBackend()
    monkeypatch.setattr(jq.job_queue, "_redis", backend)
    monkeypatch.setattr(jq.job_queue, "backend", "redis")
    monkeypatch.setattr(jq.job_queue, "production_ready", True)

    first_id = schedule_combine_flush(
        user_key="u1",
        tenant_id="t1",
        conversation_key="t1:ig:u1",
        due_at=time.time() + 30,
    )
    second_id = schedule_combine_flush(
        user_key="u1",
        tenant_id="t1",
        conversation_key="t1:ig:u1",
        due_at=time.time() + 60,
    )
    assert first_id == second_id
    job = backend.get(str(first_id))
    assert job is not None
    assert job.available_at > time.time() + 50
    assert isinstance(job, QueueJob)
    assert backend.depth()["high_priority_delayed"] == 1
    assert backend.depth()["high_priority"] == 0
