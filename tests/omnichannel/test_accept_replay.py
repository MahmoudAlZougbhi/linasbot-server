"""Accept fail-closed, replay delivery-only, and backlog must not requeue."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.models.base import Base
from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from services.omnichannel.contract import NormalizedInbound
from services.omnichannel.dlq import replay_delivery_only
from services.omnichannel.enqueue import AMBIGUOUS_ENQUEUE, enqueue_job
from services.omnichannel.store import backlog_snapshot, persist_inbound, persist_outbound


@pytest.fixture()
def db_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'omni-accept.db'}", future=True)
    Base.metadata.create_all(engine, tables=[OmnichannelInboundEvent.__table__, OmnichannelOutboundOutbox.__table__])
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        yield session


def _event(provider_event_id: str = "mid-9") -> NormalizedInbound:
    return NormalizedInbound(
        provider_event_id=provider_event_id,
        tenant_id="linas",
        account_id="page-1",
        channel="instagram",
        surface="dm",
        conversation_key="linas:instagram:u1",
        provider_timestamp=1.0,
        payload_hash="h",
        payload={"text": "hi"},
    )


def test_backlog_snapshot_does_not_enqueue(db_session, monkeypatch):
    persist_inbound(db_session, _event())
    db_session.commit()
    called = {"n": 0}

    def boom(**_kwargs):
        called["n"] += 1
        raise AssertionError("backlog must not enqueue")

    monkeypatch.setattr("services.omnichannel.accept.enqueue_generate_job", boom)
    snap = backlog_snapshot(db_session)
    assert snap["inbound"]["accepted"] == 1
    assert called["n"] == 0


def test_replay_rejects_ai_regeneration():
    with pytest.raises(PermissionError):
        replay_delivery_only({"mode": "delivery_only", "regenerate_ai": True})


def test_enqueue_fail_closed_when_redis_required_but_not_ready(monkeypatch):
    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "true")
    from types import SimpleNamespace

    monkeypatch.setattr(
        "services.job_queue.job_queue",
        SimpleNamespace(backend="memory", production_ready=False, enqueue=lambda **_k: None),
    )
    with pytest.raises(RuntimeError, match="omnichannel_queue_unavailable"):
        enqueue_job(
            logical_queue="dm_urgent",
            job_type="omnichannel_generate",
            tenant_id="linas",
            payload={},
            idempotency_key="k1",
        )


def test_enqueue_ambiguous_when_ack_lost(monkeypatch):
    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "true")
    from types import SimpleNamespace

    class Boom:
        backend = "redis"
        production_ready = True

        def enqueue(self, **_kwargs):
            raise TimeoutError("ack lost")

    monkeypatch.setattr("services.job_queue.job_queue", Boom())
    result = enqueue_job(
        logical_queue="dm_urgent",
        job_type="omnichannel_generate",
        tenant_id="linas",
        payload={},
        idempotency_key="k2",
    )
    assert result == AMBIGUOUS_ENQUEUE


def test_outbound_reuse_does_not_change_canonical_or_credits(db_session):
    first, _ = persist_outbound(
        db_session,
        tenant_id="linas",
        channel="instagram",
        surface="dm",
        account_id="page-1",
        conversation_key="linas:instagram:u1",
        inbound_event_id="in-1",
        canonical_body="hello",
        idempotency_key="ig:u1:1",
        credit_reservation_id="res-1",
        control_epoch=3,
    )
    again, created = persist_outbound(
        db_session,
        tenant_id="linas",
        channel="instagram",
        surface="dm",
        account_id="page-1",
        conversation_key="linas:instagram:u1",
        inbound_event_id="in-1",
        canonical_body="regenerated",
        idempotency_key="ig:u1:1",
        credit_reservation_id="res-2",
        control_epoch=4,
    )
    db_session.commit()
    assert created is False
    assert again.id == first.id
    assert again.canonical_body == "hello"
    assert again.credit_reservation_id == "res-1"
    assert again.control_epoch == 3
