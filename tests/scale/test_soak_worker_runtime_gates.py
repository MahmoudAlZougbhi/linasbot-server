"""Armed soak jobs must not consume OpenAI RPM or tenant inflight caps."""

from __future__ import annotations

from typing import Any

import pytest

from services.queues.models import QueueJob


class _DenyLimiter:
    def try_enter(self, **_kwargs: Any) -> Any:
        return type("D", (), {"allowed": False, "retry_after_seconds": 9.0})()

    def exit(self, **_kwargs: Any) -> None:
        return None


class _RecordingBackend:
    backend = "redis"
    production_ready = True

    def __init__(self, job: QueueJob, *, inflight: int = 0) -> None:
        self.job = job
        self.inflight = inflight
        self.soft = 0
        self.complete_n = 0
        self.reclaim_n = 0
        self.tenant_reads = 0
        self.tenant_incrs = 0

    def heartbeat(self, **_k: Any) -> None:
        return None

    def claim(self, *_a: Any, **_k: Any) -> QueueJob:
        return self.job

    def tenant_inflight(self, *_a: Any, **_k: Any) -> int:
        self.tenant_reads += 1
        return self.inflight

    def incr_tenant_inflight(self, *_a: Any, **_k: Any) -> int:
        self.tenant_incrs += 1
        return 1

    def decr_tenant_inflight(self, *_a: Any, **_k: Any) -> None:
        return None

    def reclaim_expired_leases(self, *_a: Any, **_k: Any) -> int:
        self.reclaim_n += 1
        return 0

    def requeue_soft(self, *_a: Any, **_k: Any) -> None:
        self.soft += 1

    def fail(self, *_a: Any, **_k: Any) -> bool:
        return False

    def complete(self, *_a: Any, **_k: Any) -> str:
        self.complete_n += 1
        return "ok"


def _soak_job() -> QueueJob:
    return QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "e1", "kind": "meta_dm", "_linas_soak_simulation": True, "_provider": "openai"},
    )


def _runtime(monkeypatch: pytest.MonkeyPatch, backend: _RecordingBackend):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:9/0")
    monkeypatch.setattr("services.queues.worker_runtime.RedisQueueBackend", lambda: backend)
    monkeypatch.setattr("services.omnichannel.limiter.DistributedProviderLimiter", _DenyLimiter)
    monkeypatch.setattr("services.scale.job_progress_watchdog.scan_queue", lambda *_a, **_k: {})
    from services.queues.worker_runtime import WorkerRuntime

    return WorkerRuntime("high_priority")


@pytest.mark.asyncio
async def test_soak_skips_openai_rpm_and_tenant_inflight(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _soak_job()
    backend = _RecordingBackend(job, inflight=99)
    handled: list[str] = []

    async def handler(_job: QueueJob) -> dict[str, str]:
        handled.append("ok")
        return {"ok": "true"}

    monkeypatch.setattr("services.scale.soak_arm.job_requests_soak_simulation", lambda _job: True)
    monkeypatch.setattr("services.queues.worker_runtime.get_handler", lambda _t: handler)
    runtime = _runtime(monkeypatch, backend)
    await runtime._process_one()
    assert handled == ["ok"]
    assert backend.soft == 0
    assert backend.complete_n == 1
    assert backend.tenant_reads == 0
    assert backend.tenant_incrs == 0


@pytest.mark.asyncio
async def test_production_job_still_requeues_on_openai_limiter(monkeypatch: pytest.MonkeyPatch) -> None:
    job = QueueJob.new(
        queue="high_priority",
        job_type="meta_inbound_process",
        tenant_id="linas",
        payload={"event_id": "e2", "kind": "meta_dm", "_provider": "openai"},
    )
    backend = _RecordingBackend(job, inflight=0)

    async def handler(_job: QueueJob) -> dict[str, str]:
        raise AssertionError("production job entered handler while limiter denied")

    monkeypatch.setattr("services.scale.soak_arm.job_requests_soak_simulation", lambda _job: False)
    monkeypatch.setattr("services.queues.worker_runtime.get_handler", lambda _t: handler)
    runtime = _runtime(monkeypatch, backend)
    await runtime._process_one()
    assert backend.soft == 1
    assert backend.complete_n == 0
    assert backend.tenant_incrs == 0


@pytest.mark.asyncio
async def test_housekeep_does_not_rescan_every_slot_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _soak_job()
    backend = _RecordingBackend(job)

    async def handler(_job: QueueJob) -> dict[str, str]:
        return {"ok": "true"}

    monkeypatch.setattr("services.scale.soak_arm.job_requests_soak_simulation", lambda _job: True)
    monkeypatch.setattr("services.queues.worker_runtime.get_handler", lambda _t: handler)
    runtime = _runtime(monkeypatch, backend)
    await runtime._process_one()
    first = backend.reclaim_n
    assert first == 1
    await runtime._process_one()
    assert backend.reclaim_n == first
