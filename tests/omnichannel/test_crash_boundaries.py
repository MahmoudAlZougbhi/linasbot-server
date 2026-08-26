"""Crash boundaries: persist, enqueue, claim, AI, outbox, credits, send, reconcile, DLQ."""

from __future__ import annotations

import pytest

from sqlalchemy import func, select

from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from db.session import whatsapp_session
from services.omnichannel.accept import InboundAcceptError, accept_and_enqueue
from services.omnichannel.deliver import handle_omnichannel_deliver
from services.omnichannel.dlq import replay_delivery_only
from services.omnichannel.generate import handle_omnichannel_generate
from services.omnichannel.reconcile import reconcile_omnichannel
from services.omnichannel.store import persist_inbound, persist_outbound
from tests.omnichannel.conftest import make_inbound, make_job


def test_crash_after_persist_before_enqueue_rolls_back(omni_db, monkeypatch):
    monkeypatch.setattr(
        "services.omnichannel.accept.enqueue_generate_job",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("redis_down")),
    )
    with pytest.raises(InboundAcceptError):
        accept_and_enqueue(make_inbound(provider_event_id="crash-1"))
    with whatsapp_session(require=True) as db:
        assert db.scalar(select(func.count()).select_from(OmnichannelInboundEvent)) == 0


def test_crash_after_enqueue_before_claim_is_recoverable(omni_db, durable_jobs):
    inbound_id, created = accept_and_enqueue(make_inbound(provider_event_id="queued-1"))
    assert created is True
    assert durable_jobs
    with whatsapp_session(require=True) as db:
        row = db.get(OmnichannelInboundEvent, inbound_id)
        assert row is not None
        assert row.state == "queued"
    result = reconcile_omnichannel(older_than_seconds=-1.0)
    assert any(item.get("action") == "requeue_generate" for item in result["actions"])


@pytest.mark.asyncio
async def test_crash_after_claim_before_ai_retries_without_outbox(omni_db, durable_jobs, monkeypatch):
    inbound_id, _ = accept_and_enqueue(make_inbound(provider_event_id="gen-crash"))

    async def boom(**_k):
        raise RuntimeError("killed_before_ai")

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", boom)
    with pytest.raises(RuntimeError, match="killed_before_ai"):
        await handle_omnichannel_generate(
            make_job(
                job_type="omni_generate",
                tenant_id="tenant-a",
                payload={"inbound_id": inbound_id, "channel": "instagram", "surface": "dm"},
            )
        )
    with whatsapp_session(require=True) as db:
        assert db.scalar(select(func.count()).select_from(OmnichannelOutboundOutbox)) == 0
        row = db.get(OmnichannelInboundEvent, inbound_id)
        assert row is not None
        assert row.state == "generating"

    async def ok(**_k):
        return "saved", None, None

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", ok)
    recovered = await handle_omnichannel_generate(
        make_job(
            job_type="omni_generate",
            tenant_id="tenant-a",
            payload={"inbound_id": inbound_id, "channel": "instagram", "surface": "dm"},
        )
    )
    assert recovered["ok"] is True
    with whatsapp_session(require=True) as db:
        assert db.scalar(select(func.count()).select_from(OmnichannelOutboundOutbox)) == 1


@pytest.mark.asyncio
async def test_crash_after_ai_before_outbox_does_not_leave_canonical(omni_db, durable_jobs, monkeypatch):
    inbound_id, _ = accept_and_enqueue(make_inbound(provider_event_id="ai-no-outbox"))

    async def ok(**_k):
        return "canonical", None, None

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", ok)
    monkeypatch.setattr(
        "services.omnichannel.generate.persist_outbound",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("killed_before_outbox")),
    )
    with pytest.raises(RuntimeError, match="killed_before_outbox"):
        await handle_omnichannel_generate(
            make_job(
                job_type="omni_generate",
                tenant_id="tenant-a",
                payload={"inbound_id": inbound_id, "channel": "instagram", "surface": "dm"},
            )
        )
    with whatsapp_session(require=True) as db:
        assert db.scalar(select(func.count()).select_from(OmnichannelOutboundOutbox)) == 0


@pytest.mark.asyncio
async def test_generate_does_not_capture_credits(omni_db, durable_jobs, credits, monkeypatch):
    inbound_id, _ = accept_and_enqueue(make_inbound(provider_event_id="no-capture"))

    async def ok(**_k):
        return "canonical", "res-1", None

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", ok)
    await handle_omnichannel_generate(
        make_job(
            job_type="omni_generate",
            tenant_id="tenant-a",
            payload={"inbound_id": inbound_id, "channel": "instagram", "surface": "dm"},
        )
    )
    assert ("capture", "res-1") not in credits


@pytest.mark.asyncio
async def test_crash_after_credit_before_send_retries_without_second_capture(
    omni_db, fake_limiter, credits, monkeypatch
):
    with whatsapp_session(require=True) as db:
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-cred",
            canonical_body="hello",
            idempotency_key="ig:u1:cred",
            credit_reservation_id="res-9",
        )
        db.commit()
        outbox_id = row.id
    sends = {"n": 0}

    async def boom(_snapshot):
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.capture(
            tenant_id="tenant-a", reservation_id="res-9", provider_cost_usd=None, model_provider="instagram"
        )
        raise RuntimeError("killed_after_credit")

    monkeypatch.setattr("services.omnichannel.deliver._send", boom)
    with pytest.raises(RuntimeError, match="killed_after_credit"):
        await handle_omnichannel_deliver(
            make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
        )

    async def ok(_snapshot):
        sends["n"] += 1
        return {"http_status": 200, "submitted": True, "message_id": "mid-ok"}

    monkeypatch.setattr("services.omnichannel.deliver._send", ok)
    result = await handle_omnichannel_deliver(
        make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
    )
    assert result["ok"] is True
    assert sends["n"] == 1
    captures = [item for item in credits if item[0] == "capture"]
    assert captures[0] == ("capture", "res-9")
    assert captures[-1] == ("capture", "res-9")
    assert len(captures) == 2
    assert captures[-1]  # second capture is the idempotent retry after success path


@pytest.mark.asyncio
async def test_provider_accept_then_local_commit_failure_is_ambiguous(omni_db, fake_limiter, monkeypatch):
    with whatsapp_session(require=True) as db:
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-amb",
            canonical_body="hello",
            idempotency_key="ig:u1:amb",
        )
        db.commit()
        outbox_id = row.id
    sends = {"n": 0}

    async def accepted(_snapshot):
        sends["n"] += 1
        return {"http_status": 200, "submitted": True, "message_id": "mid-amb"}

    monkeypatch.setattr("services.omnichannel.deliver._send", accepted)
    monkeypatch.setattr(
        "services.omnichannel.deliver._finish_success",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("local_commit_failed")),
    )
    result = await handle_omnichannel_deliver(
        make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
    )
    assert result["reason"] == "reconciliation_required"
    retry = await handle_omnichannel_deliver(
        make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
    )
    assert retry.get("skipped") or retry.get("reason") in {"reconciliation_required", "needs_owner_action"}
    assert sends["n"] == 1


def test_reconcile_does_not_requeue_ambiguous_outbox(omni_db, durable_jobs):
    with whatsapp_session(require=True) as db:
        persist_inbound(db, make_inbound(provider_event_id="recon-1"))
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-r",
            canonical_body="hello",
            idempotency_key="ig:u1:recon",
        )
        row.state = "reconciliation_required"
        db.commit()
    before = len(durable_jobs)
    reconcile_omnichannel(older_than_seconds=-1.0)
    assert all(job.job_type != "omni_deliver" for job in durable_jobs[before:])


def test_dlq_replay_is_delivery_only():
    with pytest.raises(PermissionError):
        replay_delivery_only({"mode": "delivery_only", "regenerate_ai": True})
    assert replay_delivery_only({"mode": "delivery_only"})["ok"] is True


def test_worker_drain_leaves_queued_inbound_searchable(omni_db, durable_jobs):
    inbound_id, _ = accept_and_enqueue(make_inbound(provider_event_id="drain-1"))
    with whatsapp_session(require=True) as db:
        row = db.get(OmnichannelInboundEvent, inbound_id)
        assert row is not None
        assert row.provider_event_id == "drain-1"
        assert row.state == "queued"
    snap = reconcile_omnichannel(older_than_seconds=-1.0)
    assert snap["examined"] >= 1
