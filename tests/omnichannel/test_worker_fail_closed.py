"""Worker must not DLQ order-wait or die on Redis lock/fail errors."""

from __future__ import annotations

import pytest

from services.queues.handlers import JobNotReady
from services.queues.models import QueueJob


class _AllowLimiter:
    def try_enter(self, **_kwargs):
        return type("D", (), {"allowed": True, "retry_after_seconds": 0})()

    def exit(self, **_kwargs):
        return None


class _RecordingBackend:
    backend = "redis"
    production_ready = True

    def __init__(self, job: QueueJob, *, fail_error: Exception | None = None):
        self.job = job
        self.fail_error = fail_error
        self.soft = 0
        self.fail_n = 0
        self.complete_n = 0

    def heartbeat(self, **_k):
        return None

    def claim(self, *_a, **_k):
        return self.job

    def tenant_inflight(self, *_a, **_k):
        return 0

    def incr_tenant_inflight(self, *_a, **_k):
        return 1

    def decr_tenant_inflight(self, *_a, **_k):
        return None

    def requeue_soft(self, *_a, **_k):
        self.soft += 1

    def fail(self, *_a, **_k):
        if self.fail_error is not None:
            raise self.fail_error
        self.fail_n += 1
        return False

    def complete(self, *_a, **_k):
        self.complete_n += 1


def _runtime(monkeypatch, backend):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:9/0")
    monkeypatch.setattr("services.queues.worker_runtime.RedisQueueBackend", lambda: backend)
    monkeypatch.setattr("services.omnichannel.limiter.DistributedProviderLimiter", _AllowLimiter)
    from services.queues.worker_runtime import WorkerRuntime

    return WorkerRuntime("high_priority")


@pytest.mark.asyncio
async def test_order_wait_soft_requeues_instead_of_fail(monkeypatch):
    job = QueueJob.new(queue="high_priority", job_type="omni_generate", tenant_id="t", payload={})
    backend = _RecordingBackend(job)

    async def wait(_job):
        raise JobNotReady("conversation_order_wait")

    monkeypatch.setattr("services.queues.worker_runtime.get_handler", lambda _t: wait)
    runtime = _runtime(monkeypatch, backend)
    await runtime._process_one()
    assert backend.soft == 1
    assert backend.fail_n == 0
    assert backend.complete_n == 0


@pytest.mark.asyncio
async def test_conversation_lock_redis_error_is_fail_closed(monkeypatch):
    job = QueueJob.new(
        queue="high_priority",
        job_type="omni_generate",
        tenant_id="t",
        payload={"_conversation_key": "t:instagram:u1"},
    )
    backend = _RecordingBackend(job)

    class BoomLock:
        def try_acquire(self, *_a, **_k):
            raise ConnectionError("closed")

    async def ok(_job):
        return {"ok": True}

    monkeypatch.setattr("services.scale.conversation_lock.ConversationLock", BoomLock)
    monkeypatch.setattr("services.queues.worker_runtime.get_handler", lambda _t: ok)
    runtime = _runtime(monkeypatch, backend)
    await runtime._process_one()
    assert backend.soft == 1
    assert backend.fail_n == 0
    assert backend.complete_n == 0


@pytest.mark.asyncio
async def test_backend_fail_redis_error_does_not_kill_slot(monkeypatch):
    job = QueueJob.new(queue="high_priority", job_type="omni_generate", tenant_id="t", payload={})
    backend = _RecordingBackend(job, fail_error=ConnectionError("closed"))

    async def boom(_job):
        raise RuntimeError("handler_boom")

    monkeypatch.setattr("services.queues.worker_runtime.get_handler", lambda _t: boom)
    runtime = _runtime(monkeypatch, backend)
    await runtime._process_one()
    assert backend.complete_n == 0


@pytest.mark.asyncio
async def test_worker_pool_survives_raising_cycle(monkeypatch):
    monkeypatch.setenv("LINAS_QUEUE_CONCURRENCY_HIGH", "2")
    from importlib import reload

    import services.omnichannel.worker_pool as pool
    import services.queues.config as config

    reload(config)
    reload(pool)
    seen = {"n": 0}
    stop = {"v": False}

    async def cycle():
        seen["n"] += 1
        if seen["n"] == 1:
            raise RuntimeError("slot_boom")
        if seen["n"] >= 6:
            stop["v"] = True

    await pool.run_bounded_pool(queue="high_priority", one_cycle=cycle, stopping=lambda: stop["v"])
    assert seen["n"] >= 6


@pytest.mark.asyncio
async def test_worker_pool_overlapping_blocking_cycles(monkeypatch):
    import threading
    from importlib import reload

    monkeypatch.setenv("LINAS_QUEUE_CONCURRENCY_HIGH", "2")
    import services.omnichannel.worker_pool as pool
    import services.queues.config as config

    reload(config)
    reload(pool)
    assert pool.concurrency_for("high_priority") == 2
    barrier = threading.Barrier(2, timeout=2.0)
    lock = threading.Lock()
    seen = {"n": 0}
    stop = {"v": False}

    async def cycle():
        barrier.wait()
        with lock:
            seen["n"] += 1
            if seen["n"] >= 2:
                stop["v"] = True

    await pool.run_bounded_pool(queue="high_priority", one_cycle=cycle, stopping=lambda: stop["v"])
    assert seen["n"] >= 2
