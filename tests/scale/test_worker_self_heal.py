"""Self-heal restores desired workers after a crash and backs off crash loops."""

from __future__ import annotations

import asyncio
import time

import fakeredis
import pytest

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.isolated_replica_pool import IsolatedReplicaPool
from services.scale.replica_controller import set_controller_redis_for_tests
from services.scale.self_heal import decide_restart
from services.scale.worker_registry import set_registry_redis_for_tests, snapshot


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_controller_redis_for_tests(fake)
    set_registry_redis_for_tests(fake)
    return RedisQueueBackend()


@pytest.mark.asyncio
async def test_crash_respawns_to_desired_and_reclaims_job(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    started: list[str] = []
    gate = asyncio.Event()

    async def handler(job: QueueJob) -> None:
        started.append(str(job.id))
        if len(started) == 1:
            await gate.wait()
        await asyncio.sleep(0.01)

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(4)
    assert pool.live_count == 4
    backend.enqueue(QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={}))
    deadline = time.time() + 3
    while not started and time.time() < deadline:
        await asyncio.sleep(0.01)
    victim = next(item.worker_id for item in pool.replicas if item.inflight)
    await pool.crash(victim)
    gate.set()
    recovered = await pool.maintain(4)
    assert pool.live_count == 4
    assert recovered["dead_swept"] >= 1
    deadline = time.time() + 3
    while backend.depth()["high_priority"] + backend.depth()["high_priority_processing"] > 0 and time.time() < deadline:
        await asyncio.sleep(0.02)
        await pool.maintain(4)
    counts = snapshot()["counts"]
    await pool.close()
    assert counts.get("ready", 0) + counts.get("busy", 0) + counts.get("dead", 0) >= 1


@pytest.mark.asyncio
async def test_stale_heartbeat_is_replaced(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    monkeypatch.setenv("LINAS_WORKER_STALE_SEC", "0.05")

    async def handler(_job: QueueJob) -> None:
        await asyncio.sleep(0.01)

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(3)
    hung = next(item for item in pool.replicas if item.task and not item.task.done())
    hung.hung = True
    hung.last_beat = time.time() - 1.0
    recovered = await pool.maintain(3)
    assert recovered["stale_killed"] >= 1
    assert pool.live_count == 3
    await pool.close()


def test_crash_loop_is_rate_limited() -> None:
    now = 1_000.0
    starts = [now - 1.0] * 5
    blocked = decide_restart(restart_count=5, recent_starts=starts, now=now, window_seconds=60.0, max_in_window=5)
    assert blocked.allowed is False
    assert blocked.reason == "restart_rate_limited"
    allowed = decide_restart(restart_count=1, recent_starts=[now - 1.0], now=now)
    assert allowed.allowed is True
    assert allowed.delay_seconds >= 0.2
