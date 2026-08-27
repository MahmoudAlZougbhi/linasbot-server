"""Local smoke: long/blocking jobs stay owned, complete once, never land on DLQ."""

from __future__ import annotations

import time

import fakeredis
import pytest

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.isolated_replica_pool import IsolatedReplicaPool
from services.scale.job_progress import set_progress_redis_for_tests
from services.scale.replica_controller import set_controller_redis_for_tests
from services.scale.worker_registry import set_registry_redis_for_tests


def teardown_function() -> None:
    set_progress_redis_for_tests(None)
    set_controller_redis_for_tests(None)
    set_registry_redis_for_tests(None)


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    monkeypatch.setenv("LINAS_QUEUE_LEASE_TTL_SECONDS", "1")
    monkeypatch.setenv("LINAS_QUEUE_LEASE_HEARTBEAT_SECONDS", "0.15")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_progress_redis_for_tests(fake)
    set_controller_redis_for_tests(fake)
    set_registry_redis_for_tests(fake)
    return RedisQueueBackend()


@pytest.mark.asyncio
async def test_local_smoke_blocking_jobs_complete_without_dlq_or_duplicate(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    seen: list[str] = []

    async def handler(job: QueueJob) -> None:
        seen.append(job.id)
        time.sleep(1.6)

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(2)
    job_ids = []
    for _ in range(3):
        job = QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={})
        backend.enqueue(job)
        job_ids.append(job.id)
    dlq_before = int(backend.depth()["high_priority_dlq"])
    deadline = time.time() + 20
    while time.time() < deadline:
        depth = backend.depth()
        pending = (
            int(depth["high_priority"]) + int(depth["high_priority_processing"]) + int(depth["high_priority_delayed"])
        )
        if pending == 0 and len(seen) >= 3:
            break
        await pool.maintain(2)
        time.sleep(0.05)
    await pool.close()
    depth = backend.depth()
    assert int(depth["high_priority_dlq"]) == dlq_before
    assert int(depth["high_priority_processing"]) == 0
    assert sorted(seen) == sorted(job_ids)
    assert len(seen) == len(set(seen))
    for job_id in job_ids:
        stored = backend.get(job_id)
        assert stored is not None
        assert stored.status == "completed"
        leftover = backend._r.lrange(backend._k("dlq", "high_priority"), 0, -1) or []
        assert job_id not in leftover
