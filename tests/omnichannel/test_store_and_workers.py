"""Inbound persist, outbox reuse, and worker inflight wiring."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.models.base import Base
from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from services.omnichannel.contract import NormalizedInbound
from services.omnichannel.store import persist_inbound, persist_outbound


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'omni.db'}", future=True)
    Base.metadata.create_all(engine, tables=[OmnichannelInboundEvent.__table__, OmnichannelOutboundOutbox.__table__])
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        yield session


def test_duplicate_inbound_does_not_create_second_row(db_session: Session):
    event = NormalizedInbound(
        provider_event_id="mid-1",
        tenant_id="linas",
        account_id="page-1",
        channel="instagram",
        surface="dm",
        conversation_key="linas:instagram:u1",
        provider_timestamp=1.0,
        payload_hash="abc",
        payload={"text": "hi"},
    )
    first, created = persist_inbound(db_session, event)
    second, created2 = persist_inbound(db_session, event)
    db_session.commit()
    assert created is True
    assert created2 is False
    assert first.id == second.id


def test_outbound_retry_reuses_canonical_body(db_session: Session):
    row, created = persist_outbound(
        db_session,
        tenant_id="linas",
        channel="instagram",
        surface="dm",
        account_id="page-1",
        conversation_key="linas:instagram:u1",
        inbound_event_id="ocb-1",
        canonical_body="saved reply",
        idempotency_key="ig:u1:1",
    )
    again, created2 = persist_outbound(
        db_session,
        tenant_id="linas",
        channel="instagram",
        surface="dm",
        account_id="page-1",
        conversation_key="linas:instagram:u1",
        inbound_event_id="ocb-1",
        canonical_body="different regenerated text",
        idempotency_key="ig:u1:1",
    )
    db_session.commit()
    assert created is True
    assert created2 is False
    assert again.canonical_body == "saved reply"


@pytest.mark.asyncio
async def test_worker_pool_runs_configured_slots(monkeypatch):
    monkeypatch.setenv("LINAS_QUEUE_CONCURRENCY_BACKGROUND", "3")
    from importlib import reload

    import services.omnichannel.worker_pool as pool
    import services.queues.config as config

    reload(config)
    reload(pool)
    seen = {"n": 0}
    stop = {"v": False}

    async def cycle():
        seen["n"] += 1
        if seen["n"] >= 3:
            stop["v"] = True

    await pool.run_bounded_pool(queue="background", one_cycle=cycle, stopping=lambda: stop["v"])
    assert pool.concurrency_for("background") == 3
    assert seen["n"] >= 3


def test_meta_comment_enqueue_queue_is_background(monkeypatch):
    captured = {}

    class Queue:
        backend = "redis"
        production_ready = True

        def enqueue(self, **kwargs):
            captured.update(kwargs)
            return type("J", (), {"id": "job-1"})()

    monkeypatch.setattr("services.scale.meta_ingress.redis_required", lambda: True)
    monkeypatch.setattr("services.job_queue.job_queue", Queue())
    from services.scale import meta_ingress

    job_id = meta_ingress._try_enqueue(
        event_id="e1",
        kind="meta_comment",
        tenant_id="linas",
        conversation_key="linas:facebook:c1",
    )
    assert job_id == "job-1"
    assert captured["queue"] == "background"
    dm = meta_ingress._try_enqueue(
        event_id="e2",
        kind="meta_dm",
        tenant_id="linas",
        conversation_key="linas:instagram:u1",
    )
    assert dm == "job-1"
    assert captured["queue"] == "high_priority"


def _inbound(**overrides):
    base = dict(
        provider_event_id="mid-shared",
        tenant_id="linas",
        account_id="page-1",
        channel="instagram",
        surface="dm",
        conversation_key="linas:instagram:u1",
        provider_timestamp=1.0,
        payload_hash="abc",
        payload={"text": "hi"},
    )
    base.update(overrides)
    return NormalizedInbound(**base)


def test_same_provider_event_id_is_tenant_isolated(db_session: Session):
    first, created = persist_inbound(db_session, _inbound(tenant_id="tenant-a"))
    second, created2 = persist_inbound(db_session, _inbound(tenant_id="tenant-b"))
    db_session.commit()
    assert created is True
    assert created2 is True
    assert first.id != second.id
    assert first.tenant_id == "tenant-a"
    assert second.tenant_id == "tenant-b"


def test_conversation_order_blocks_newer_event(db_session: Session):
    from services.omnichannel.store import conversation_has_earlier_unfinished

    older, _ = persist_inbound(
        db_session, _inbound(provider_event_id="old", provider_timestamp=1.0, payload_hash="old")
    )
    newer, _ = persist_inbound(
        db_session, _inbound(provider_event_id="new", provider_timestamp=2.0, payload_hash="new")
    )
    db_session.commit()
    assert conversation_has_earlier_unfinished(
        db_session,
        conversation_key="linas:instagram:u1",
        provider_timestamp=2.0,
        inbound_id=newer.id,
    )
    assert not conversation_has_earlier_unfinished(
        db_session,
        conversation_key="linas:instagram:u1",
        provider_timestamp=1.0,
        inbound_id=older.id,
    )


def test_mirror_only_inbound_is_not_requeued(db_session: Session):
    from services.omnichannel.store import list_unfinished_inbound

    persist_inbound(
        db_session,
        _inbound(provider_event_id="mirror", payload={"_mirror_only": True}, payload_hash="m"),
    )
    persist_inbound(db_session, _inbound(provider_event_id="real", payload={"text": "x"}, payload_hash="r"))
    db_session.commit()
    rows = list_unfinished_inbound(db_session, older_than_seconds=-1.0)
    assert [row.provider_event_id for row in rows] == ["real"]


def test_ambiguous_outbound_is_not_auto_retried(db_session: Session):
    from services.omnichannel.store import list_retryable_outbound

    row, _ = persist_outbound(
        db_session,
        tenant_id="linas",
        channel="instagram",
        surface="dm",
        account_id="page-1",
        conversation_key="linas:instagram:u1",
        inbound_event_id="ocb-amb",
        canonical_body="hello",
        idempotency_key="ig:u1:amb",
    )
    row.state = "reconciliation_required"
    db_session.commit()
    assert list_retryable_outbound(db_session) == []
