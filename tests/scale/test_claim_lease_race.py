"""Claim sets the lease in the same Redis script as the pop so reclaim cannot steal it."""

from __future__ import annotations

import threading

import fakeredis

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    return RedisQueueBackend()


def test_reclaim_during_save_does_not_steal_live_claim(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"k": "v"})
    backend.enqueue(job)
    original_save = backend._save
    stolen: list[int] = []

    def save_and_reclaim(claimed: QueueJob) -> None:
        stolen.append(backend.reclaim_expired_leases("high_priority"))
        original_save(claimed)

    backend._save = save_and_reclaim  # type: ignore[method-assign]
    claimed = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert claimed is not None
    assert stolen == [0]
    assert backend._r.exists(backend._k("lease", claimed.id))
    assert claimed.status == "processing"
    assert backend.complete(claimed).startswith("ok")


def test_incomplete_activate_is_not_treated_as_dead_worker(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
    backend.enqueue(job)
    backend._r.rpoplpush(backend._k("queue", "high_priority"), backend._k("processing", "high_priority"))
    assert backend.get(job.id).status == "queued"
    assert not backend._r.exists(backend._k("lease", job.id))
    assert backend.reclaim_expired_leases("high_priority") == 0
    stored = backend.get(job.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.last_error is None
    assert stored.attempts == 0
    assert job.id in backend._r.lrange(backend._k("processing", "high_priority"), 0, -1)


def test_peer_reclaim_loop_cannot_expire_a_live_claim(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
    backend.enqueue(job)
    stop = threading.Event()
    hits: list[int] = []

    def peer() -> None:
        while not stop.is_set():
            hits.append(backend.reclaim_expired_leases("high_priority"))

    thread = threading.Thread(target=peer, daemon=True)
    thread.start()
    try:
        claimed = backend.claim("high_priority", worker_id="w-live", timeout=1)
        assert claimed is not None
        assert claimed.last_error is None
        assert backend.get(claimed.id).status == "processing"
        assert backend.complete(claimed).startswith("ok")
    finally:
        stop.set()
        thread.join(timeout=1)
    assert hits
    assert max(hits) == 0
