"""Lease is liveness, not a job duration cap. Heartbeat runs off the event loop."""

from __future__ import annotations

import time

import fakeredis

from services.queues.lease_heartbeat import bind_claimed_heartbeat
from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.job_progress import set_progress_redis_for_tests


def teardown_function() -> None:
    set_progress_redis_for_tests(None)


def _backend(monkeypatch, *, ttl: str = "1") -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    monkeypatch.setenv("LINAS_QUEUE_LEASE_TTL_SECONDS", ttl)
    monkeypatch.setenv("LINAS_QUEUE_LEASE_HEARTBEAT_SECONDS", "0.15")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_progress_redis_for_tests(fake)
    return RedisQueueBackend()


def _claim(backend: RedisQueueBackend, worker_id: str = "w1") -> QueueJob:
    job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
    backend.enqueue(job)
    claimed = backend.claim("high_priority", worker_id=worker_id, timeout=1)
    assert claimed is not None
    return claimed


def test_job_longer_than_lease_ttl_is_not_reclaimed_while_heartbeat_runs(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="1")
    claimed = _claim(backend)
    beat = bind_claimed_heartbeat(
        backend=backend,
        job=claimed,
        worker_id="w1",
        interval_seconds=0.15,
    )
    try:
        time.sleep(2.3)
        assert backend.reclaim_expired_leases("high_priority") == 0
        stored = backend.get(claimed.id)
        assert stored is not None
        assert stored.status == "processing"
        assert stored.lease_token == claimed.lease_token
        assert backend.complete(claimed).startswith("ok")
    finally:
        beat.stop()


def test_multi_minute_stand_in_same_owner_with_heartbeat(monkeypatch) -> None:
    """Compressed stand-in for a multi-minute Luna/Tera call (TTL 1s, run 3s)."""
    backend = _backend(monkeypatch, ttl="1")
    claimed = _claim(backend, worker_id="w-long")
    beat = bind_claimed_heartbeat(
        backend=backend,
        job=claimed,
        worker_id="w-long",
        interval_seconds=0.2,
    )
    try:
        time.sleep(3.1)
        assert backend.reclaim_expired_leases("high_priority") == 0
        assert backend.get(claimed.id).lease_owner == "w-long"
        assert backend.complete(claimed).startswith("ok")
    finally:
        beat.stop()


def test_dead_worker_without_heartbeat_is_reclaimed(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="1")
    claimed = _claim(backend, worker_id="w-dead")
    deadline = time.time() + 3.0
    while time.time() < deadline and backend._r.exists(backend._k("lease", claimed.id)):
        time.sleep(0.05)
    assert not backend._r.exists(backend._k("lease", claimed.id))
    assert backend.reclaim_expired_leases("high_priority") == 1
    again = backend.claim("high_priority", worker_id="w-live", timeout=1)
    assert again is not None
    assert again.id == claimed.id
    assert again.lease_owner == "w-live"
    assert again.lease_token != claimed.lease_token
    assert backend.complete(claimed) == "stale_owner"
    assert backend.complete(again).startswith("ok")


def test_blocking_section_does_not_prevent_lease_refresh(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="1")
    claimed = _claim(backend)
    beat = bind_claimed_heartbeat(
        backend=backend,
        job=claimed,
        worker_id="w1",
        interval_seconds=0.15,
    )
    try:
        time.sleep(2.2)
        assert backend._r.exists(backend._k("lease", claimed.id))
        assert backend.reclaim_expired_leases("high_priority") == 0
    finally:
        beat.stop()
    assert backend.complete(claimed).startswith("ok")


def test_temporary_heartbeat_lag_within_ttl_is_not_reclaimed(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="2")
    claimed = _claim(backend)
    time.sleep(0.8)
    assert backend.reclaim_expired_leases("high_priority") == 0
    assert backend.refresh_lease(claimed.id, "w1", claimed.lease_token) is True
    time.sleep(0.4)
    assert backend.reclaim_expired_leases("high_priority") == 0
    assert backend.complete(claimed).startswith("ok")


def test_refresh_restores_missing_lease_while_same_owner(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="2")
    claimed = _claim(backend)
    backend._r.delete(backend._k("lease", claimed.id))
    assert backend.refresh_lease(claimed.id, "w1", claimed.lease_token) is True
    assert backend._r.get(backend._k("lease", claimed.id)) == claimed.lease_wire()
    assert backend.reclaim_expired_leases("high_priority") == 0
    assert backend.complete(claimed).startswith("ok")


def test_refresh_does_not_restore_after_new_owner_claims(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="1")
    worker_a = _claim(backend, worker_id="w-a")
    backend._r.delete(backend._k("lease", worker_a.id))
    assert backend.reclaim_expired_leases("high_priority") == 1
    worker_b = backend.claim("high_priority", worker_id="w-b", timeout=1)
    assert worker_b is not None
    assert backend.refresh_lease(worker_a.id, "w-a", worker_a.lease_token) is False
    assert backend._r.get(backend._k("lease", worker_a.id)) == worker_b.lease_wire()
    assert backend.complete(worker_b).startswith("ok")


def test_heartbeat_retries_after_temporary_refresh_failure(monkeypatch) -> None:
    backend = _backend(monkeypatch, ttl="1")
    claimed = _claim(backend)
    calls = {"n": 0}
    real = backend.refresh_lease

    def flaky(job_id: str, worker_id: str, lease_token: str = "") -> bool:
        calls["n"] += 1
        if calls["n"] == 1:
            return False
        return real(job_id, worker_id, lease_token)

    monkeypatch.setattr(backend, "refresh_lease", flaky)
    beat = bind_claimed_heartbeat(
        backend=backend,
        job=claimed,
        worker_id="w1",
        interval_seconds=0.15,
    )
    try:
        time.sleep(2.3)
        assert backend.reclaim_expired_leases("high_priority") == 0
        assert backend.complete(claimed).startswith("ok")
        assert calls["n"] >= 2
    finally:
        beat.stop()
