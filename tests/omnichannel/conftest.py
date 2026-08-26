"""Shared SQLite + fake-queue fixtures for omnichannel handler tests."""

from __future__ import annotations

import fakeredis
import pytest

from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from db.session import get_engine, reset_engine_for_tests
from services.omnichannel.contract import NormalizedInbound
from services.omnichannel.limiter import DistributedProviderLimiter
from services.queues.models import QueueJob
from services.scale.provider_limiter import ProviderLimiter


def make_inbound(**overrides) -> NormalizedInbound:
    base = dict(
        provider_event_id="evt-1",
        tenant_id="tenant-a",
        account_id="acct-1",
        channel="instagram",
        surface="dm",
        conversation_key="tenant-a:instagram:u1",
        provider_timestamp=1.0,
        payload_hash="h1",
        payload={"text": "hi", "control_epoch": 0},
    )
    base.update(overrides)
    return NormalizedInbound(**base)


def make_job(*, job_type: str, tenant_id: str, payload: dict) -> QueueJob:
    return QueueJob.new(queue="high_priority", job_type=job_type, tenant_id=tenant_id, payload=payload)


@pytest.fixture()
def omni_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'omni-handlers.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = get_engine(require=True)
    OmnichannelInboundEvent.__table__.create(engine, checkfirst=True)
    OmnichannelOutboundOutbox.__table__.create(engine, checkfirst=True)
    yield
    reset_engine_for_tests()


@pytest.fixture()
def durable_jobs(monkeypatch):
    jobs: list[QueueJob] = []

    class Queue:
        backend = "redis"
        production_ready = True

        def enqueue(self, **kwargs):
            job = QueueJob.new(
                queue=kwargs["queue"],
                job_type=kwargs["job_type"],
                tenant_id=kwargs["tenant_id"],
                payload=kwargs.get("payload") or {},
                idempotency_key=kwargs.get("idempotency_key"),
            )
            jobs.append(job)
            return job

    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "true")
    monkeypatch.setattr("services.job_queue.job_queue", Queue())
    return jobs


@pytest.fixture()
def fake_limiter(monkeypatch):
    redis_client = fakeredis.FakeRedis(decode_responses=True)

    def factory(*_args, **_kwargs):
        return DistributedProviderLimiter(redis_client, inner=ProviderLimiter(redis_client))

    monkeypatch.setattr("services.omnichannel.deliver.DistributedProviderLimiter", factory)
    return redis_client


@pytest.fixture()
def credits(monkeypatch):
    log: list[tuple[str, str]] = []

    class Ledger:
        def capture(self, **kwargs):
            log.append(("capture", str(kwargs.get("reservation_id") or "")))
            return {"duplicate": log.count(("capture", str(kwargs.get("reservation_id") or ""))) > 1, "op": "capture"}

        def release(self, **kwargs):
            log.append(("release", str(kwargs.get("reservation_id") or "")))
            return {"op": "release"}

    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", Ledger())
    return log
