"""Channel paths, gates, operator takeover, duplicates, and tenant isolation."""

from __future__ import annotations

import pytest

from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from db.session import whatsapp_session
from services.omnichannel.accept import InboundAcceptError, accept_and_enqueue
from services.omnichannel.channel_tiktok import deliver_tiktok
from services.omnichannel.classify import classify_http_delivery
from services.omnichannel.deliver import handle_omnichannel_deliver
from services.omnichannel.gates import TIKTOK_DM_GATE_REASON, tiktok_dm_live_allowed
from services.omnichannel.generate import handle_omnichannel_generate
from services.omnichannel.operator_enqueue import enqueue_operator_reply
from services.omnichannel.store import persist_outbound
from tests.omnichannel.conftest import make_inbound, make_job

CHANNELS = (
    ("instagram", "dm"),
    ("instagram", "comment"),
    ("facebook", "dm"),
    ("facebook", "comment"),
    ("whatsapp", "dm"),
    ("tiktok", "comment"),
    ("tiktok", "dm"),
    ("web_chat", "web_chat"),
)


@pytest.mark.asyncio
@pytest.mark.parametrize(("channel", "surface"), CHANNELS)
async def test_channel_accept_generate_deliver_is_idempotent(
    omni_db, durable_jobs, fake_limiter, monkeypatch, channel, surface
):
    inbound_id, created = accept_and_enqueue(
        make_inbound(
            provider_event_id=f"{channel}-{surface}-1",
            channel=channel,
            surface=surface,
            conversation_key=f"tenant-a:{channel}:{surface}:u1",
            payload={"text": "hi", "control_epoch": 0},
        )
    )
    assert created is True

    async def gen(**_k):
        if channel == "tiktok" and surface == "dm":
            return "", None, TIKTOK_DM_GATE_REASON
        return "canonical", None, None

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", gen)
    gen_result = await handle_omnichannel_generate(
        make_job(
            job_type="omni_generate",
            tenant_id="tenant-a",
            payload={"inbound_id": inbound_id, "channel": channel, "surface": surface},
        )
    )
    if channel == "tiktok" and surface == "dm":
        assert gen_result["skipped"] is True
        assert gen_result["reason"] == TIKTOK_DM_GATE_REASON
        allowed, reason = tiktok_dm_live_allowed(None)
        assert allowed is False
        assert reason == TIKTOK_DM_GATE_REASON
        return

    sends = {"n": 0, "bodies": []}

    async def send(snapshot):
        sends["n"] += 1
        sends["bodies"].append(snapshot["canonical_body"])
        return {"http_status": 200, "submitted": True, "message_id": f"mid-{sends['n']}"}

    monkeypatch.setattr("services.omnichannel.deliver._send", send)
    outbox_id = gen_result["outbox_id"]
    first = await handle_omnichannel_deliver(
        make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
    )
    second = await handle_omnichannel_deliver(
        make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
    )
    assert first["ok"] is True
    assert second.get("skipped") is True
    assert sends["n"] == 1
    assert sends["bodies"] == ["canonical"]


def test_duplicate_webhook_does_not_enqueue_twice(omni_db, durable_jobs):
    event = make_inbound(provider_event_id="dup-1")
    first_id, created = accept_and_enqueue(event)
    again_id, created2 = accept_and_enqueue(event)
    assert created is True
    assert created2 is False
    assert first_id == again_id
    assert len(durable_jobs) == 1


def test_tenant_isolation_same_provider_event(omni_db, durable_jobs):
    a, _ = accept_and_enqueue(make_inbound(tenant_id="tenant-a", provider_event_id="shared"))
    b, _ = accept_and_enqueue(
        make_inbound(
            tenant_id="tenant-b",
            provider_event_id="shared",
            conversation_key="tenant-b:instagram:u1",
        )
    )
    assert a != b
    with whatsapp_session(require=True) as db:
        left = db.get(OmnichannelInboundEvent, a)
        right = db.get(OmnichannelInboundEvent, b)
        assert left is not None and right is not None
        assert left.tenant_id != right.tenant_id


@pytest.mark.asyncio
async def test_out_of_order_conversation_waits(omni_db, durable_jobs, monkeypatch):
    older, _ = accept_and_enqueue(make_inbound(provider_event_id="old", provider_timestamp=1.0, payload_hash="old"))
    newer, _ = accept_and_enqueue(make_inbound(provider_event_id="new", provider_timestamp=2.0, payload_hash="new"))

    async def ok(**_k):
        return "canonical", None, None

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", ok)
    from services.queues.handlers import JobNotReady

    with pytest.raises(JobNotReady, match="conversation_order_wait"):
        await handle_omnichannel_generate(
            make_job(
                job_type="omni_generate",
                tenant_id="tenant-a",
                payload={"inbound_id": newer, "channel": "instagram", "surface": "dm"},
            )
        )
    await handle_omnichannel_generate(
        make_job(
            job_type="omni_generate",
            tenant_id="tenant-a",
            payload={"inbound_id": older, "channel": "instagram", "surface": "dm"},
        )
    )


@pytest.mark.asyncio
async def test_operator_takeover_suppresses_racing_ai(omni_db, durable_jobs, fake_limiter, monkeypatch):
    inbound_id, _ = accept_and_enqueue(make_inbound(provider_event_id="race-1"))
    enqueue_operator_reply(
        tenant_id="tenant-a",
        channel="instagram",
        surface="dm",
        account_id="acct-1",
        conversation_key="tenant-a:instagram:u1",
        text="human reply",
        control_epoch=2,
    )
    sends = {"ai": 0, "op": 0}

    async def send(snapshot):
        if snapshot.get("source") == "operator":
            sends["op"] += 1
        else:
            sends["ai"] += 1
        return {"http_status": 200, "submitted": True, "message_id": "mid"}

    monkeypatch.setattr("services.omnichannel.deliver._send", send)

    async def gen(**_k):
        return "ai reply", None, None

    monkeypatch.setattr("services.omnichannel.generate._generate_canonical", gen)
    gen_result = await handle_omnichannel_generate(
        make_job(
            job_type="omni_generate",
            tenant_id="tenant-a",
            payload={"inbound_id": inbound_id, "channel": "instagram", "surface": "dm"},
        )
    )
    assert gen_result.get("skipped") is True
    assert gen_result.get("reason") == "operator_takeover"
    op_jobs = [job for job in durable_jobs if job.job_type == "omni_deliver"]
    assert op_jobs
    await handle_omnichannel_deliver(
        make_job(
            job_type="omni_deliver",
            tenant_id="tenant-a",
            payload={"outbox_id": op_jobs[0].payload["outbox_id"]},
        )
    )
    assert sends["ai"] == 0
    assert sends["op"] == 1


@pytest.mark.asyncio
async def test_permanent_400_does_not_retry_forever(omni_db, fake_limiter, monkeypatch):
    with whatsapp_session(require=True) as db:
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-400",
            canonical_body="hello",
            idempotency_key="ig:u1:400",
        )
        db.commit()
        outbox_id = row.id

    async def bad(_snapshot):
        return {"http_status": 400, "submitted": False, "error": "bad_request"}

    monkeypatch.setattr("services.omnichannel.deliver._send", bad)
    with pytest.raises(Exception, match="definitive|PermanentJobError|client"):
        await handle_omnichannel_deliver(
            make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
        )
    with whatsapp_session(require=True) as db:
        row = db.get(OmnichannelOutboundOutbox, outbox_id)
        assert row is not None
        assert row.state == "dead_letter"


@pytest.mark.asyncio
async def test_meta_429_613_retries_and_honors_retry_after(omni_db, fake_limiter, monkeypatch):
    with whatsapp_session(require=True) as db:
        row, _ = persist_outbound(
            db,
            tenant_id="tenant-a",
            channel="instagram",
            surface="dm",
            account_id="acct-1",
            conversation_key="tenant-a:instagram:u1",
            inbound_event_id="in-429",
            canonical_body="hello",
            idempotency_key="ig:u1:429",
        )
        db.commit()
        outbox_id = row.id

    async def throttled(_snapshot):
        return {
            "http_status": 429,
            "code": "613",
            "submitted": False,
            "headers": {"Retry-After": "4", "X-App-Usage": '{"call_count":90}'},
        }

    monkeypatch.setattr("services.omnichannel.deliver._send", throttled)
    with pytest.raises(RuntimeError, match="transient"):
        await handle_omnichannel_deliver(
            make_job(job_type="omni_deliver", tenant_id="tenant-a", payload={"outbox_id": outbox_id})
        )
    with whatsapp_session(require=True) as db:
        row = db.get(OmnichannelOutboundOutbox, outbox_id)
        assert row is not None
        assert row.state == "rate_limited"
        assert row.next_retry_at is not None


def test_enqueue_failure_is_not_swallowed(omni_db, monkeypatch):
    monkeypatch.setattr(
        "services.omnichannel.accept.enqueue_generate_job",
        lambda **_k: (_ for _ in ()).throw(RuntimeError("redis_down")),
    )
    with pytest.raises(InboundAcceptError):
        accept_and_enqueue(make_inbound(provider_event_id="swallowed"))


def test_tiktok_connection_reset_is_not_submitted():
    decision = classify_http_delivery(connection_reset_before_submit=True, submitted=False)
    assert decision.kind == "transient"
    assert decision.retryable is True


@pytest.mark.asyncio
async def test_tiktok_exception_before_submit_is_not_marked_submitted(monkeypatch):
    from contextlib import contextmanager

    class Conn:
        open_id = "oid"
        tenant_id = "tenant-a"

    class Repo:
        def get_connection(self, *_a, **_k):
            return Conn()

    @contextmanager
    def fake_session(*, require=True):
        class Dummy:
            def commit(self) -> None:
                return None

        yield Dummy()

    monkeypatch.setattr("services.omnichannel.channel_tiktok.whatsapp_session", fake_session)
    monkeypatch.setattr("services.omnichannel.channel_tiktok.TikTokRepository", lambda _s: Repo())
    monkeypatch.setattr("services.omnichannel.channel_tiktok.tiktok_dm_live_allowed", lambda _c: (True, ""))

    async def token(*_a, **_k):
        return "tok"

    monkeypatch.setattr("services.omnichannel.channel_tiktok.ensure_fresh_token", token)

    async def boom(**_k):
        raise ConnectionResetError("reset")

    monkeypatch.setattr("services.tiktok_business.messaging.send_business_message", boom)
    result = await deliver_tiktok(
        {
            "tenant_id": "tenant-a",
            "account_id": "conn-1",
            "surface": "dm",
            "canonical_body": "hi",
            "conversation_key": "tenant-a:tiktok:c1",
        }
    )
    assert result["submitted"] is False
    assert result.get("reset_before_submit") is True
