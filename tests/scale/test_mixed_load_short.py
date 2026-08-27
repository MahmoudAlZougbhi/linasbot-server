"""Short mixed-load: crash under work, reclaim, restore desired. Not product latency."""

from __future__ import annotations

import asyncio
import time

import fakeredis
import pytest

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.isolated_replica_pool import IsolatedReplicaPool
from services.scale.replica_controller import set_controller_redis_for_tests
from services.scale.worker_registry import set_registry_redis_for_tests


@pytest.mark.asyncio
async def test_crash_under_load_restores_desired_without_lost_jobs(monkeypatch) -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_controller_redis_for_tests(fake)
    set_registry_redis_for_tests(fake)
    backend = RedisQueueBackend()
    completed: list[str] = []

    async def handler(job: QueueJob) -> None:
        await asyncio.sleep(0.03)
        completed.append(str(job.id))

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(4)
    for i in range(20):
        backend.enqueue(QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"i": i}))
    await asyncio.sleep(0.05)
    live = [item for item in pool.replicas if item.task and not item.task.done()]
    await pool.crash(live[0].worker_id)
    deadline = time.time() + 6
    while time.time() < deadline:
        await pool.maintain(4)
        depth = backend.depth()
        pending = int(depth.get("high_priority") or 0) + int(depth.get("high_priority_processing") or 0)
        if len(set(completed)) >= 20 and pending == 0:
            break
        await asyncio.sleep(0.02)
    assert pool.live_count == 4
    assert len(set(completed)) == 20
    await pool.close()
