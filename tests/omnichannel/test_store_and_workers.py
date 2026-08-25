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
