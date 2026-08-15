"""Second-review P1 fixes: SFU reservation bind, ACK/billing split, AI heartbeat, job fence."""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
from services.smart_followup.constants import CLAIM_STALE_SECONDS
from services.smart_followup.types import FollowUpConversationView, FollowUpSendResult
from services.smart_followup.worker_job import process_one_followup_job
from services.web_chat.delivery_outbox import ack_pending_messages
from services.web_chat.followup_delivery import deliver_web_followup_message, reconcile_followup_credit
from services.web_chat.operation_fsm import OperationState, stable_operation_key
from services.web_chat.processor import WebChatError, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_chat_acceptance_fsm import _widget_and_visitor
from tests.test_web_followup_web_delivery import _reserve_followup_credit
from tests.web_chat_acceptance_billing import assert_acceptance_ledger_equation, fetch_pg_ledger_snapshot
from tests.web_chat_acceptance_support import patch_acceptance_eligibility, patch_web_chat_store, seed_acceptance_widget
from tests.web_chat_runtime_support import run_threaded_barrier_async


def _operation_state(postgres_url: str, *, tenant_id: str, operation_key: str) -> str:
    engine = __import__("sqlalchemy").create_engine(postgres_url, pool_pre_ping=True)
    with engine.connect() as conn:
        row = conn.execute(
            __import__("sqlalchemy").text(
                "SELECT state, reservation_id FROM web_chat_operations WHERE tenant_id = :tid AND operation_key = :key"
            ),
            {"tid": tenant_id, "key": operation_key},
        ).fetchone()
    assert row is not None
    return str(row[0]), row[1]


@pytest.mark.asyncio
async def test_sfu_delivery_binds_reservation_and_captures_once(
    web_chat_pg_store, acceptance_pg_ha_env, monkeypatch
) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    store = web_chat_pg_store
    monkeypatch.setattr("services.web_chat.followup_delivery.web_chat_store", store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-sfu-bind"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    idem = "sfu:bind:1"
    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)
    from services.web_chat.persistence import PersistOutcome, PersistResult

    monkeypatch.setattr(
        "services.web_chat.followup_delivery.persist_web_chat_message",
        AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv")),
    )
    result = await deliver_web_followup_message(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        user_id=f"web:{visitor_id}",
        conversation_id=f"web:{tenant_id}:{visitor_id}",
        reply_text="Follow-up",
        idempotency_key=idem,
        widget_key=widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    assert result.status == "delivered"
    assert result.billing_captured is True
    op_key = stable_operation_key(session_id=visitor_id, client_key=idem)
    state, bound_reservation = _operation_state(acceptance_pg_ha_env, tenant_id=tenant_id, operation_key=op_key)
    assert state == OperationState.COMPLETE.value
    assert bound_reservation == reservation_id


@pytest.mark.asyncio
async def test_ack_before_capture_does_not_complete_billing(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    visitor_id = visitor.id
    idem = "sfu:ack-race:1"
    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)
    from services.web_chat.persistence import PersistOutcome, PersistResult

    monkeypatch.setattr(
        "services.web_chat.followup_delivery.persist_web_chat_message",
        AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv")),
    )

    capture_calls = 0
    original_capture = __import__(
        "services.credit_ledger_service", fromlist=["credit_ledger_service"]
    ).credit_ledger_service.capture

    def flaky_capture(*args, **kwargs):
        nonlocal capture_calls
        capture_calls += 1
        if capture_calls == 1:
            raise RuntimeError("capture commit lost")
        return original_capture(*args, **kwargs)

    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service.capture", flaky_capture)

    delivered = await deliver_web_followup_message(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        user_id=f"web:{visitor_id}",
        conversation_id=f"web:{tenant_id}:{visitor_id}",
        reply_text="Ack race",
        idempotency_key=idem,
        widget_key=widget.widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    assert delivered.billing_pending is True
    op_key = stable_operation_key(session_id=visitor_id, client_key=idem)

    ack_pending_messages(
        session_id=visitor_id,
        widget=widget,
        session_authority=bundle.authority_token,
        message_ids=[idem],
        store=store,
    )
    state_after_ack, _ = _operation_state(acceptance_pg_ha_env, tenant_id=tenant_id, operation_key=op_key)
    assert state_after_ack == OperationState.BILLING_PENDING.value

    assert reconcile_followup_credit(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        idempotency_key=idem,
        reservation_id=reservation_id,
    )
    state_final, _ = _operation_state(acceptance_pg_ha_env, tenant_id=tenant_id, operation_key=op_key)
    assert state_final == OperationState.COMPLETE.value
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "reserve": 1, "capture": 1},
        captured=1,
    )


def test_slow_ai_heartbeat_prevents_second_provider_call(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)

    monkeypatch.setattr("services.web_chat.operation_lease.LEASE_TTL_SECONDS", 3)
    monkeypatch.setattr("services.web_chat.operation_heartbeat.HEARTBEAT_INTERVAL_SECONDS", 1)

    ai_lock = threading.Lock()
    ai_calls = 0
    ai_started = threading.Event()

    async def slow_ai(*_args, **_kwargs):
        nonlocal ai_calls
        with ai_lock:
            ai_calls += 1
        ai_started.set()
        await asyncio.sleep(4.5)
        return MagicMock(reply="Slow reply")

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=slow_ai),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            side_effect=lambda **_kwargs: __import__(
                "services.web_chat.persistence", fromlist=["PersistResult", "PersistOutcome"]
            ).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=f"web:{widget.tenant_id}:{bundle.session_id}",
            )
        ),
    )

    async def worker_turn() -> str:
        for _ in range(200):
            try:
                return await process_web_chat_message(
                    widget=widget,
                    visitor_session=visitor,
                    user_text="Slow hello",
                    store=store,
                    idempotency_key="slow-ai-heartbeat",
                )
            except WebChatError as exc:
                if exc.code != "operation_in_progress":
                    raise
                await asyncio.sleep(0.05)
        raise AssertionError("slow AI turn never settled")

    replies = run_threaded_barrier_async(workers=2, coro_factory=worker_turn, timeout=30.0)
    assert ai_calls == 1
    assert all(reply == "Slow reply" for reply in replies)

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert snapshot.ops.get("reserve", 0) == 1
    assert snapshot.ops.get("capture", 0) == 1
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "reserve": 1, "capture": 1},
        captured=1,
    )


@pytest.mark.asyncio
async def test_sfu_stale_worker_cannot_deliver_after_reclaim(tmp_path, monkeypatch) -> None:

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpSequence
    from db.session import reset_engine_for_tests
    from services.credit_ledger_service import CreditLedgerService
    from services.entitlements_service import EntitlementsStore
    from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT

    url = f"sqlite:///{tmp_path / 'sfu_fence.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
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

    now = datetime.now(UTC)
    seq = WhatsAppSmartFollowUpSequence(
        tenant_id="tenant-b",
        channel=SOURCE_CHANNEL_WEB_CHAT,
        connection_id="wk-b",
        conversation_id="web:tenant-b:visitor-fence",
        trigger_outbound_intent_id="trigger-fence",
        channel_context={"social_sender_id": "visitor-fence"},
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
        conversation_id="web:tenant-b:visitor-fence",
        channel_context={"social_sender_id": "visitor-fence"},
        sequence_id=seq.id,
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=now,
        status="claimed",
        control_epoch=1,
        idempotency_key="sfu:fence:1",
        claimed_at=now - timedelta(seconds=CLAIM_STALE_SECONDS + 5),
        claimed_by="worker-stale",
        attempt_count=1,
    )
    db.add(job)
    db.commit()
    job_id = job.id

    job.status = "claimed"
    job.claimed_by = "worker-fresh"
    job.attempt_count = 2
    job.claimed_at = datetime.now(UTC)
    db.commit()
    db.close()

    conv = FollowUpConversationView(
        channel=SOURCE_CHANNEL_WEB_CHAT,
        tenant_id="tenant-b",
        conversation_id="web:tenant-b:visitor-fence",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="visitor-fence",
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
        return_value=FollowUpSendResult(status="sent", reason="sent", provider_message_id="sfu:fence:1")
    )
    monkeypatch.setattr("services.smart_followup.worker_job.get_channel_adapter", lambda _channel: mock_adapter)

    stale_out = await process_one_followup_job(job_id=job_id, worker_id="worker-stale")
    assert stale_out["status"] == "claim_lost"
    mock_adapter.send_followup.assert_not_awaited()

    fresh_out = await process_one_followup_job(job_id=job_id, worker_id="worker-fresh")
    assert fresh_out["status"] in {"sent", "reconciliation_required"}
    mock_adapter.send_followup.assert_awaited_once()

    reset_engine_for_tests()
