"""Burst / spike rounds against a real Redis queue and replica pool."""

from __future__ import annotations

import asyncio
import time

import fakeredis
import pytest

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.isolated_replica_pool import IsolatedReplicaPool
from services.scale.replica_controller import set_controller_redis_for_tests
from services.scale.shutdown import ShutdownCoordinator


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((p / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_controller_redis_for_tests(fake)
    return RedisQueueBackend()


async def _run_round(
    *,
    backend: RedisQueueBackend,
    workers: int,
    jobs: int,
    work_s: float,
) -> dict[str, float]:
    latencies: list[float] = []
    completed = 0

    async def handler(job: QueueJob) -> None:
        nonlocal completed
        await asyncio.sleep(work_s)
        latencies.append((time.time() - float(job.created_at)) * 1000.0)
        completed += 1

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(workers)
    t0 = time.time()
    for i in range(jobs):
        backend.enqueue(
            QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"i": i})
        )
    deadline = time.time() + 15
    while completed < jobs and time.time() < deadline:
        await asyncio.sleep(0.01)
    duration = max(0.001, time.time() - t0)
    depth = backend.depth()
    await pool.close()
    return {
        "jobs": float(jobs),
        "completed": float(completed),
        "workers": float(workers),
        "ingress_per_sec": jobs / duration,
        "complete_per_sec": completed / duration,
        "queue_depth_end": float(depth.get("high_priority") or 0),
        "dlq": float(depth.get("high_priority_dlq") or 0),
        "p50_ms": _pct(latencies, 50),
        "p95_ms": _pct(latencies, 95),
        "p99_ms": _pct(latencies, 99),
        "lost": float(jobs - completed),
    }


@pytest.mark.asyncio
async def test_burst_rounds_do_not_lose_jobs(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    rounds = []
    for workers, jobs, work_s in (
        (2, 20, 0.01),
        (4, 40, 0.01),
        (8, 80, 0.005),
    ):
        rounds.append(await _run_round(backend=backend, workers=workers, jobs=jobs, work_s=work_s))
    assert all(row["lost"] == 0 for row in rounds)
    assert all(row["dlq"] == 0 for row in rounds)
    assert rounds[-1]["complete_per_sec"] >= rounds[0]["complete_per_sec"]


@pytest.mark.asyncio
async def test_graceful_shutdown_finishes_inflight(monkeypatch) -> None:
    coordinator = ShutdownCoordinator()
    entered = asyncio.Event()
    released = asyncio.Event()

    async def handler(_job: QueueJob) -> None:
        entered.set()
        await released.wait()

    backend = _backend(monkeypatch)
    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(1)
    backend.enqueue(QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={}))
    await asyncio.wait_for(entered.wait(), timeout=3)
    coordinator.begin_drain()
    assert coordinator.accept_queue_work is False
    released.set()
    await pool.close()
    assert coordinator.wait_for_idle(timeout_seconds=1) is True
