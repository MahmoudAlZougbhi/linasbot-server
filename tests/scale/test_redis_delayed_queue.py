"""Delayed queue parking must not busy-spin the claim loop."""

from __future__ import annotations

import fakeredis

from services.queues.models import QueueJob


def test_future_job_is_parked_not_claimed(monkeypatch) -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = rb.RedisQueueBackend()
    job = QueueJob.new(
        queue="high_priority",
        job_type="combine_flush",
        tenant_id="t1",
        payload={"user_key": "u1"},
        available_at=10**12,
    )
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed is None
    assert backend.depth()["high_priority"] == 0
    assert backend.depth()["high_priority_delayed"] == 1
    assert backend.oldest_age_seconds("high_priority") > 0


def test_due_job_is_promoted_and_claimed(monkeypatch) -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = rb.RedisQueueBackend()
    job = QueueJob.new(
        queue="high_priority",
        job_type="combine_flush",
        tenant_id="t1",
        payload={"user_key": "u1"},
        available_at=0,
    )
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed is not None
    assert claimed.id == job.id


def test_idempotent_enqueue_returns_same_job(monkeypatch) -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    backend = rb.RedisQueueBackend()
    first = QueueJob.new(
        queue="high_priority",
        job_type="combine_flush",
        tenant_id="t1",
        payload={},
        idempotency_key="combine_flush:u1",
    )
    a = backend.enqueue(first)
    b = backend.enqueue(
        QueueJob.new(
            queue="high_priority",
            job_type="combine_flush",
            tenant_id="t1",
            payload={},
            idempotency_key="combine_flush:u1",
        )
    )
    assert a.id == b.id
