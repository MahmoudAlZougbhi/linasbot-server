"""Deliver must enter/exit the distributed limiter; worker limiter is fail-closed."""

from __future__ import annotations

import pytest

from db.session import whatsapp_session
from services.omnichannel.deliver import handle_omnichannel_deliver
from services.omnichannel.store import persist_outbound
from services.queues.models import QueueJob
from tests.omnichannel.conftest import make_job


@pytest.mark.asyncio
async def test_deliver_calls_try_enter_and_exits_inflight(omni_db, fake_limiter, monkeypatch):
    sends = {"n": 0}

    async def _send(snapshot):
        sends["n"] += 1
        assert int(fake_limiter.get("linas:prov:inflight:meta") or 0) == 1
        return {"http_status": 200, "submitted": True, "message_id": "mid-1"}

    monkeypatch.setattr("services.omnichannel.deliver._send", _send)
    with whatsapp_session(require=True) as db:
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-1",
            canonical_body="hello",
            idempotency_key="ig:u1:lim",
        )
        db.commit()
        outbox_id = row.id
    result = await handle_omnichannel_deliver(
        make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
    )
    assert result["ok"] is True
    assert sends["n"] == 1
    assert int(fake_limiter.get("linas:prov:inflight:meta") or 0) == 0


@pytest.mark.asyncio
async def test_deliver_defers_when_limiter_rejects(omni_db, fake_limiter, monkeypatch):
    from services.omnichannel.limiter import DistributedProviderLimiter
    from services.scale.provider_limiter import ProviderLimiter

    limiter = DistributedProviderLimiter(fake_limiter, inner=ProviderLimiter(fake_limiter))
    limiter.record_throttle(provider="meta", account_id="acct-1", endpoint="dm", retry_after_seconds=9)
    sends = {"n": 0}

    async def _send(_snapshot):
        sends["n"] += 1
        return {"http_status": 200, "submitted": True, "message_id": "mid-x"}

    monkeypatch.setattr("services.omnichannel.deliver._send", _send)
    with whatsapp_session(require=True) as db:
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-2",
            canonical_body="hello",
            idempotency_key="ig:u1:lim2",
        )
        db.commit()
        outbox_id = row.id
    with pytest.raises(RuntimeError, match="limiter:"):
        await handle_omnichannel_deliver(
            make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
        )
    assert sends["n"] == 0
    with whatsapp_session(require=True) as db:
        from db.models.omnichannel import OmnichannelOutboundOutbox

        row = db.get(OmnichannelOutboundOutbox, outbox_id)
        assert row is not None
        assert row.state == "rate_limited"


def test_worker_provider_gate_is_fail_closed(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:9/0")

    class DummyBackend:
        backend = "redis"
        production_ready = True

    monkeypatch.setattr("services.queues.worker_runtime.RedisQueueBackend", DummyBackend)

    class BoomLimiter:
        def try_enter(self, **_kwargs):
            raise RuntimeError("redis_down")

    monkeypatch.setattr("services.omnichannel.limiter.DistributedProviderLimiter", BoomLimiter)
    from services.queues.worker_runtime import WorkerRuntime

    runtime = WorkerRuntime("high_priority")
    job = QueueJob.new(queue="high_priority", job_type="omni_deliver", tenant_id="t", payload={})
    delay = runtime._provider_gate(job)
    assert delay is not None
    assert delay >= 1.0


@pytest.mark.asyncio
async def test_worker_claim_connection_error_is_fail_closed(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:9/0")

    class BoomBackend:
        backend = "redis"
        production_ready = True

        def heartbeat(self, **_k):
            return None

        def claim(self, *_a, **_k):
            raise ConnectionError("closed")

    monkeypatch.setattr("services.queues.worker_runtime.RedisQueueBackend", lambda: BoomBackend())
    from services.queues.worker_runtime import WorkerRuntime

    runtime = WorkerRuntime("high_priority")
    await runtime._process_one()
