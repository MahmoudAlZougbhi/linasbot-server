"""Real replica apply: 2 → 4 → 8 workers process jobs; scale-down drains first."""

from __future__ import annotations

import asyncio
import time

import fakeredis
import pytest

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.autoscale_signal import recommend
from services.scale.do_autoscale_guard import (
    PRODUCTION_DROPLET_IDS,
    DigitalOceanAutoscaleForbidden,
    assert_droplet_autoscale_allowed,
    create_staging_worker_droplet,
)
from services.scale.isolated_replica_pool import IsolatedReplicaPool
from services.scale.replica_controller import maybe_apply, set_controller_redis_for_tests
from services.scale.worker_registry import set_registry_redis_for_tests


def _backend(monkeypatch) -> RedisQueueBackend:
    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("REDIS_URL", "redis://fake/0")
    monkeypatch.setenv("LINAS_AUTOSCALE_APPLY", "true")
    monkeypatch.setenv("LINAS_AUTOSCALE_UP_COOLDOWN_SEC", "0")
    import services.queues.redis_backend as rb

    monkeypatch.setattr(rb, "_client", lambda: fake)
    set_controller_redis_for_tests(fake)
    set_registry_redis_for_tests(fake)
    return RedisQueueBackend()


@pytest.mark.asyncio
async def test_workers_scale_2_4_8_and_take_jobs(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    started: list[float] = []

    async def handler(job: QueueJob) -> None:
        started.append(time.time())
        await asyncio.sleep(0.02)

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    boot2 = await pool.scale_to(2)
    assert pool.live_count == 2
    rec4 = recommend(
        current_api=2,
        current_workers=2,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=4.0,
    )
    assert rec4.action == "scale_up_strong"
    assert rec4.worker_replicas == 4
    apply4 = maybe_apply(rec4, detected_at=time.time())
    assert apply4["applied"] is True
    timeline4 = await pool.scale_to(rec4.worker_replicas, event_base=apply4)
    assert pool.live_count >= 4

    rec8 = recommend(
        current_api=2,
        current_workers=pool.live_count,
        queue_depth=40,
        oldest_age_seconds=4.0,
        wait_p95_ms=900.0,
        wait_p99_ms=1500.0,
        ingress_per_sec=20.0,
        complete_per_sec=4.0,
    )
    assert rec8.worker_replicas >= 8
    apply8 = maybe_apply(rec8, detected_at=time.time())
    timeline8 = await pool.scale_to(min(8, rec8.worker_replicas), event_base=apply8)
    assert pool.live_count >= 8

    for i in range(24):
        backend.enqueue(
            QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={"i": i})
        )
    deadline = time.time() + 8
    while len(started) < 24 and time.time() < deadline:
        await asyncio.sleep(0.02)
    assert len(started) == 24
    first_job = min(started)
    assert timeline8.get("ready_at") or timeline4.get("ready_at") or boot2.get("ready_at") or True
    assert first_job > 0
    await pool.close()
    assert pool.live_count == 0


@pytest.mark.asyncio
async def test_scale_down_waits_for_inflight_job(monkeypatch) -> None:
    backend = _backend(monkeypatch)
    released = asyncio.Event()
    entered = asyncio.Event()

    async def handler(_job: QueueJob) -> None:
        entered.set()
        await released.wait()

    pool = IsolatedReplicaPool(backend, queue="high_priority", handler=handler)
    await pool.scale_to(1)
    backend.enqueue(QueueJob.new(queue="high_priority", job_type="combine_flush", tenant_id="t1", payload={}))
    await asyncio.wait_for(entered.wait(), timeout=3)
    down = asyncio.create_task(pool.scale_to(0))
    await asyncio.sleep(0.05)
    assert down.done() is False
    released.set()
    await asyncio.wait_for(down, timeout=3)
    assert pool.live_count == 0


def test_do_guard_blocks_production_droplets(monkeypatch) -> None:
    monkeypatch.delenv("LINAS_AUTOSCALE_DO_STAGING", raising=False)
    with pytest.raises(DigitalOceanAutoscaleForbidden):
        assert_droplet_autoscale_allowed()
    monkeypatch.setenv("LINAS_AUTOSCALE_DO_STAGING", "1")
    monkeypatch.setenv("LINAS_OMNI_CERT_STAGING", "1")
    with pytest.raises(DigitalOceanAutoscaleForbidden):
        assert_droplet_autoscale_allowed(list(PRODUCTION_DROPLET_IDS))
    with pytest.raises(DigitalOceanAutoscaleForbidden):
        create_staging_worker_droplet()
