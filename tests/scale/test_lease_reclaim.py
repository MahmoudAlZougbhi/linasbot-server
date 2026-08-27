"""Dead-worker jobs are reclaimed; completed jobs are not replayed."""

from __future__ import annotations

import fakeredis

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    return RedisQueueBackend()


def test_expired_lease_is_requeued(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"k": "v"})
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w-dead", timeout=1)
    assert claimed is not None
    backend._r.delete(backend._k("lease", claimed.id))
    reclaimed = backend.reclaim_expired_leases("high_priority")
    assert reclaimed == 1
    again = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert again is not None
    assert again.id == claimed.id


def test_complete_removes_requeued_copy(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed is not None
    backend.complete(claimed)
    leftover = backend.claim("high_priority", worker_id="w2", timeout=1)
    assert leftover is None


def test_refresh_requires_matching_token(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id="w1", timeout=1)
    assert claimed is not None
    assert backend.refresh_lease(claimed.id, "w1") is False
    assert backend.refresh_lease(claimed.id, "w1", claimed.lease_token) is True
    assert backend.refresh_lease(claimed.id, "w-other", claimed.lease_token) is False


def test_persist_then_kill_before_job_does_not_lose_work(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="meta_inbound_process", tenant_id="t1", payload={"n": 1})
    backend.enqueue(job)
    # API node dies after enqueue; worker on another node still claims.
    claimed = backend.claim("high_priority", worker_id="w-node3", timeout=1)
    assert claimed is not None
    assert claimed.payload["n"] == 1
