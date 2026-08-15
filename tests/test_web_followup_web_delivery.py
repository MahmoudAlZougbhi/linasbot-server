"""Idempotent Smart Follow-Up delivery tests for website chat."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
from services.smart_followup.adapters.web import WebFollowUpAdapter
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.web_chat.config_models import WebChatWidgetConfig
from services.web_chat.followup_delivery import deliver_web_followup_message
from services.web_chat.processor import compose_web_user_id
from tests.web_chat_acceptance_billing import seed_acceptance_credit_ledger
from tests.web_chat_acceptance_support import patch_acceptance_eligibility, seed_acceptance_widget, seed_widget_config


def _reserve_followup_credit(*, tenant_id: str, idem: str) -> str:
    from services.credit_ledger_service import credit_ledger_service
    from services.smart_followup.constants import OPERATION_TYPE
    from services.smart_followup.idempotency import canonical_sfu_credit_request_id

    seed_acceptance_credit_ledger(tenant_id=tenant_id)
    return credit_ledger_service.reserve(
        tenant_id=tenant_id,
        user_id=None,
        credits=1,
        operation_type=OPERATION_TYPE,
        request_id=canonical_sfu_credit_request_id(idem),
    )


def _web_followup_fixtures(store, *, visitor_id: str = "visitor-2", idem: str = "idem-1"):
    widget = WebChatWidgetConfig(
        tenant_id="tenant-b",
        widget_key="wk-b",
        site_url="https://shop.example.com",
        enabled=True,
        created_at=time.time(),
        updated_at=time.time(),
    )
    from services.web_chat.store_pg import WebChatPgStore

    if isinstance(store, WebChatPgStore):
        widget = seed_widget_config(store, widget)
        from services.web_chat.session_authority import issue_session_authority

        bundle = issue_session_authority(widget=widget)
        store.get_or_create_visitor(
            session_id=visitor_id,
            widget=widget,
            greeting="Hi",
            authority_hash=bundle.authority_hash,
        )
    else:
        store.get_or_create_visitor(session_id=visitor_id, widget=widget, greeting="Hi")
    job = WhatsAppSmartFollowUpJob(
        tenant_id="tenant-b",
        channel="web_chat",
        connection_id="wk-b",
        conversation_id=f"web:tenant-b:{visitor_id}",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key=idem,
    )
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id="tenant-b",
        conversation_id=f"web:tenant-b:{visitor_id}",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id=visitor_id,
    )
    return widget, job, conv


@pytest.mark.asyncio
async def test_web_followup_same_idempotency_key_delivers_once(web_chat_pg_store, monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    store = web_chat_pg_store
    monkeypatch.setattr("services.web_chat.followup_delivery.web_chat_store", store)
    monkeypatch.setattr("services.smart_followup.adapters.web.web_chat_store", store)
    _, job, conv = _web_followup_fixtures(store, visitor_id="visitor-idem", idem="sfu:seq:1")

    from services.web_chat.persistence import PersistOutcome, PersistResult

    save_mock = AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv"))
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", save_mock)
    adapter = WebFollowUpAdapter()
    job.reservation_id = _reserve_followup_credit(tenant_id="tenant-b", idem="sfu:seq:1")

    first = await adapter.send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Checking in",
        idempotency_key="sfu:seq:1",
    )
    second = await adapter.send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Checking in",
        idempotency_key="sfu:seq:1",
    )

    assert first.status == "sent"
    assert first.reason == "sent"
    assert second.status == "sent"
    assert second.reason == "duplicate_delivery"
    save_mock.assert_awaited_once()
    session = store.get_visitor("visitor-idem")
    assert session is not None
    assert len(session.pending_assistant) == 1
    assert session.pending_assistant[0].id == "sfu:seq:1"


@pytest.mark.asyncio
async def test_web_followup_crash_after_persist_before_queue_recovers(web_chat_pg_store, monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    store = web_chat_pg_store
    monkeypatch.setattr("services.web_chat.followup_delivery.web_chat_store", store)
    monkeypatch.setattr("services.smart_followup.adapters.web.web_chat_store", store)
    _, job, conv = _web_followup_fixtures(store, visitor_id="visitor-crash", idem="sfu:crash:1")

    from services.web_chat.persistence import PersistOutcome, PersistResult

    save_mock = AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv"))
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", save_mock)
    job.reservation_id = _reserve_followup_credit(tenant_id="tenant-b", idem="sfu:crash:1")
    adapter = WebFollowUpAdapter()
    original_queue = store.queue_assistant_message
    queue_attempts = 0

    def queue_once_then_succeed(session_id: str, content: str, *, idempotency_key: str | None = None) -> bool:
        nonlocal queue_attempts
        queue_attempts += 1
        if queue_attempts == 1:
            raise RuntimeError("crash before queue persisted")
        return original_queue(session_id, content, idempotency_key=idempotency_key)

    monkeypatch.setattr(store, "queue_assistant_message", queue_once_then_succeed)

    failed = await adapter.send_followup(
        session=MagicMock(), job=job, conv=conv, reply_text="Checking in", idempotency_key="sfu:crash:1"
    )
    recovered = await adapter.send_followup(
        session=MagicMock(), job=job, conv=conv, reply_text="Checking in", idempotency_key="sfu:crash:1"
    )

    assert failed.status == "failed"
    assert recovered.status == "sent"
    assert save_mock.await_count == 2
    session = store.get_visitor("visitor-crash")
    assert session is not None
    assert len(session.pending_assistant) == 1


@pytest.mark.asyncio
async def test_deliver_web_followup_message_is_idempotent(web_chat_pg_store, monkeypatch) -> None:
    store = web_chat_pg_store
    monkeypatch.setattr("services.web_chat.followup_delivery.web_chat_store", store)
    widget = seed_widget_config(
        store,
        WebChatWidgetConfig(
            tenant_id="tenant-b",
            widget_key="wk-b",
            site_url="https://shop.example.com",
            enabled=True,
            created_at=time.time(),
            updated_at=time.time(),
        ),
    )
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id="visitor-deliver",
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    from services.web_chat.persistence import PersistOutcome, PersistResult

    save_mock = AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv"))
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", save_mock)
    reservation_id = _reserve_followup_credit(tenant_id="tenant-b", idem="sfu:deliver:1")

    first = await deliver_web_followup_message(
        tenant_id="tenant-b",
        visitor_id="visitor-deliver",
        user_id=compose_web_user_id("visitor-deliver"),
        conversation_id="web:tenant-b:visitor-deliver",
        reply_text="Hello again",
        idempotency_key="sfu:deliver:1",
        widget_key=widget.widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    second = await deliver_web_followup_message(
        tenant_id="tenant-b",
        visitor_id="visitor-deliver",
        user_id=compose_web_user_id("visitor-deliver"),
        conversation_id="web:tenant-b:visitor-deliver",
        reply_text="Hello again",
        idempotency_key="sfu:deliver:1",
        widget_key=widget.widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )

    assert first.status == "delivered"
    assert second.status == "already_delivered"
    save_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_sfu_worker_duplicate_visible_delivery_never_releases_reservation(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob, WhatsAppSmartFollowUpSequence
    from db.session import reset_engine_for_tests
    from services.credit_ledger_service import CreditLedgerService
    from services.entitlements_service import EntitlementsStore
    from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT
    from services.smart_followup.types import FollowUpConversationView
    from services.smart_followup.worker_job import process_one_followup_job

    os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
    url = f"sqlite:///{tmp_path / 'sfu_web_credit.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    db = Session()

    ent_store = EntitlementsStore(root=tmp_path / "ents")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", ent_store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", ent_store)
    ledger = CreditLedgerService(root=tmp_path / "ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    ent_store.set_plan(tenant_id="tenant-b", plan_id="starter", status="active", source="admin")
    ledger.ensure_period_grant("tenant-b")
    start_total = ledger.get_balance("tenant-b")

    now = datetime.now(UTC)
    seq = WhatsAppSmartFollowUpSequence(
        tenant_id="tenant-b",
        channel=SOURCE_CHANNEL_WEB_CHAT,
        connection_id="wk-b",
        conversation_id="web:tenant-b:visitor-credit",
        trigger_outbound_intent_id="trigger-credit-1",
        channel_context={"social_sender_id": "visitor-credit"},
        trigger_ai_sent_at=now,
        control_epoch=1,
        settings_version=1,
        status="active",
    )
    db.add(seq)
    db.flush()
    job = WhatsAppSmartFollowUpJob(
        tenant_id="tenant-b",
        channel=SOURCE_CHANNEL_WEB_CHAT,
        connection_id="wk-b",
        conversation_id="web:tenant-b:visitor-credit",
        channel_context={"social_sender_id": "visitor-credit"},
        sequence_id=seq.id,
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=now,
        status="claimed",
        control_epoch=1,
        idempotency_key="sfu:credit:1",
        claimed_at=now,
        claimed_by="worker-1",
    )
    db.add(job)
    db.commit()

    conv = FollowUpConversationView(
        channel=SOURCE_CHANNEL_WEB_CHAT,
        tenant_id="tenant-b",
        conversation_id="web:tenant-b:visitor-credit",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="visitor-credit",
    )
    monkeypatch.setattr(
        "services.smart_followup.worker_job.generate_followup_text",
        AsyncMock(return_value="Checking in"),
    )
    monkeypatch.setattr(
        "services.smart_followup.worker_job.evaluate_job_eligibility_async",
        AsyncMock(return_value=(True, "ok", conv)),
    )
    mock_adapter = MagicMock()
    mock_adapter.load_conversation = MagicMock(return_value=conv)
    mock_adapter.send_followup = AsyncMock(
        return_value=FollowUpSendResult(
            status="sent",
            reason="duplicate_delivery",
            provider_message_id="sfu:credit:1",
        )
    )
    monkeypatch.setattr("services.smart_followup.worker_job.get_channel_adapter", lambda _channel: mock_adapter)

    out = await process_one_followup_job(job_id=job.id, worker_id="worker-1")
    db.refresh(job)

    assert out["status"] == "reconciliation_required"
    assert job.credits_captured == 0
    assert ledger.get_balance("tenant-b") == start_total - 1
    assert ledger.get_reserved("tenant-b") == 1

    db.close()
    reset_engine_for_tests()


@pytest.mark.asyncio
async def test_acceptance_followup_exactly_one_pending_after_concurrent_retries(
    tmp_path, monkeypatch, acceptance_ha_env
) -> None:
    """Acceptance: replayed delivery keeps a single outbox row for one idempotency key."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    from services.web_chat.session_authority import issue_session_authority
    from services.web_chat.store_pg import WebChatPgStore

    store = WebChatPgStore()
    monkeypatch.setattr("services.web_chat.followup_delivery.web_chat_store", store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id="visitor-replay",
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    from services.web_chat.persistence import PersistOutcome, PersistResult

    save_mock = AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv"))
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", save_mock)
    adapter = WebFollowUpAdapter()
    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem="sfu:replay:1")

    reasons = []
    for _ in range(5):
        result = await adapter.send_followup(
            session=MagicMock(),
            job=WhatsAppSmartFollowUpJob(
                tenant_id=tenant_id,
                channel="web_chat",
                connection_id=widget_key,
                conversation_id=f"web:{tenant_id}:visitor-replay",
                channel_context={"social_sender_id": "visitor-replay"},
                sequence_id="seq-1",
                step_index=1,
                goal="gentle_check_in",
                delay_minutes=30,
                due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                control_epoch=1,
                idempotency_key="sfu:replay:1",
                reservation_id=reservation_id,
            ),
            conv=FollowUpConversationView(
                channel="web_chat",
                tenant_id=tenant_id,
                conversation_id=f"web:{tenant_id}:visitor-replay",
                connection_id=widget_key,
                control_epoch=1,
                control_state="AI_ACTIVE",
                service_window_opens_at=None,
                last_inbound_at=None,
                social_sender_id="visitor-replay",
            ),
            reply_text="Checking in",
            idempotency_key="sfu:replay:1",
        )
        reasons.append(result.reason)

    assert reasons.count("sent") == 1
    assert reasons.count("duplicate_delivery") == 4
    save_mock.assert_awaited_once()
    session = store.get_visitor("visitor-replay")
    assert session is not None
    assert len(session.pending_assistant) == 1
