"""Acceptance tests for delivery blockers: cross-tenant, recovery, release, projection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
from services.smart_followup.adapters.web import WebFollowUpAdapter
from services.smart_followup.types import FollowUpConversationView
from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle
from services.web_chat.followup_delivery import deliver_web_followup_message
from services.web_chat.operation_fsm import OperationFsmError
from services.web_chat.persistence import PersistFailure, PersistOutcome, PersistResult
from services.web_chat.processor import compose_web_user_id
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_followup_web_delivery import _reserve_followup_credit
from tests.web_chat_acceptance_billing import (
    fetch_pg_ledger_snapshot,
)
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_web_chat_store,
    seed_acceptance_widget,
)


@pytest.mark.asyncio
async def test_cross_tenant_followup_job_has_zero_side_effects(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    monkeypatch.setattr("services.smart_followup.adapters.web.web_chat_store", store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-cross-tenant"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    persist_mock = AsyncMock(
        return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id=f"web:{tenant_id}:{visitor_id}")
    )
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)

    job = WhatsAppSmartFollowUpJob(
        tenant_id="evil-tenant",
        channel="web_chat",
        connection_id=widget_key,
        conversation_id=f"web:evil-tenant:{visitor_id}",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key="sfu:cross:1",
    )
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id="evil-tenant",
        conversation_id=f"web:evil-tenant:{visitor_id}",
        connection_id=widget_key,
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id=visitor_id,
    )
    result = await WebFollowUpAdapter().send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Poison",
        idempotency_key="sfu:cross:1",
    )
    assert result.status == "failed"
    assert result.reason == "cross_tenant_session"
    persist_mock.assert_not_awaited()
    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 0
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert snapshot.ops.get("reserve", 0) == 0


@pytest.mark.asyncio
async def test_followup_same_key_queue_recovery_one_visible_message(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-same-key"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    idem = "sfu:same-key:1"
    persist_mock = AsyncMock(
        return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id=f"web:{tenant_id}:{visitor_id}")
    )
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)

    attempts = 0
    original_queue = store.queue_assistant_message

    def queue_fail_once(session_id: str, content: str, *, idempotency_key: str | None = None) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("queue lost")
        return original_queue(session_id, content, idempotency_key=idempotency_key)

    monkeypatch.setattr(store, "queue_assistant_message", queue_fail_once)

    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)

    with pytest.raises(RuntimeError, match="queue lost"):
        await deliver_web_followup_message(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=compose_web_user_id(visitor_id),
            conversation_id=f"web:{tenant_id}:{visitor_id}",
            reply_text="Recover",
            idempotency_key=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )

    recovered = await deliver_web_followup_message(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        user_id=compose_web_user_id(visitor_id),
        conversation_id=f"web:{tenant_id}:{visitor_id}",
        reply_text="Recover",
        idempotency_key=idem,
        widget_key=widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    assert recovered.status == "delivered"
    assert persist_mock.await_count == 2
    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 1
    assert session.pending_assistant[0].id == idem


@pytest.mark.asyncio
async def test_followup_crash_after_reply_ready_before_persist_recovers(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """REPLY_READY resume must re-confirm Firestore before outbox — one projection, one message."""
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-reply-ready-crash"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    idem = "sfu:reply-ready:crash:1"
    persist_calls = 0

    async def fail_once_persist(**_kwargs):
        nonlocal persist_calls
        persist_calls += 1
        if persist_calls == 1:
            raise PersistFailure("firestore_error", "down")
        return PersistResult(outcome=PersistOutcome.CREATED, conversation_id=f"web:{tenant_id}:{visitor_id}")

    persist_mock = AsyncMock(side_effect=fail_once_persist)
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)

    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)

    with pytest.raises(PersistFailure, match="down"):
        await deliver_web_followup_message(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=compose_web_user_id(visitor_id),
            conversation_id=f"web:{tenant_id}:{visitor_id}",
            reply_text="Recover after crash",
            idempotency_key=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )

    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 0

    recovered = await deliver_web_followup_message(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        user_id=compose_web_user_id(visitor_id),
        conversation_id=f"web:{tenant_id}:{visitor_id}",
        reply_text="Recover after crash",
        idempotency_key=idem,
        widget_key=widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    assert recovered.status == "delivered"
    assert persist_calls == 2
    persist_mock.assert_awaited()
    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 1
    assert session.pending_assistant[0].id == idem
    assert session.pending_assistant[0].content == "Recover after crash"


def test_release_ack_loss_stays_release_pending(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    from services.credit_ledger_service import credit_ledger_service

    handle = WebChatCreditHandle(tenant_id="biz", reservation_id=None, request_id="web:release:1")
    handle.reserve()
    reservation_id = handle.reservation_id
    assert reservation_id

    original_release = credit_ledger_service.release
    calls = 0

    def fail_once_release(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("release ack lost")
        return original_release(**kwargs)

    monkeypatch.setattr(credit_ledger_service, "release", fail_once_release)
    assert handle.reconcile_release() is False
    assert handle.state == CreditFsmState.RELEASE_PENDING
    assert handle.reservation_id == reservation_id

    assert handle.reconcile_release() is True
    assert handle.state == CreditFsmState.RELEASED
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz")
    assert snapshot.reserved == 0
    assert snapshot.available == start_total
    assert snapshot.ops.get("release", 0) == 1


@pytest.mark.asyncio
async def test_followup_missing_reservation_fails_closed(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-no-reservation"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    persist_mock = AsyncMock(
        return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id=f"web:{tenant_id}:{visitor_id}")
    )
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)

    with pytest.raises(OperationFsmError) as exc_info:
        await deliver_web_followup_message(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=compose_web_user_id(visitor_id),
            conversation_id=f"web:{tenant_id}:{visitor_id}",
            reply_text="Blocked",
            idempotency_key="sfu:no-reservation:1",
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
        )
    assert exc_info.value.code == "reservation_required"

    persist_mock.assert_not_awaited()
    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 0
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert snapshot.ops.get("reserve", 0) == 0
    assert snapshot.ops.get("capture", 0) == 0


@pytest.mark.asyncio
async def test_followup_outbox_before_durable_visible_failpoint_converges_billing(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """Crash after outbox insert must converge to one capture; never free visible delivery."""
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-outbox-failpoint"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    idem = "sfu:outbox-failpoint:1"
    persist_mock = AsyncMock(
        return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id=f"web:{tenant_id}:{visitor_id}")
    )
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", persist_mock)
    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)

    monkeypatch.setenv("WEB_CHAT_FOLLOWUP_FAILPOINT", "after_outbox_before_durable_visible")
    with pytest.raises(RuntimeError, match="failpoint:after_outbox_before_durable_visible"):
        await deliver_web_followup_message(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=compose_web_user_id(visitor_id),
            conversation_id=f"web:{tenant_id}:{visitor_id}",
            reply_text="Crash boundary",
            idempotency_key=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )

    mid = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert mid.ops.get("capture", 0) == 0
    assert mid.reserved == 1
    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 1

    monkeypatch.delenv("WEB_CHAT_FOLLOWUP_FAILPOINT", raising=False)
    recovered = await deliver_web_followup_message(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        user_id=compose_web_user_id(visitor_id),
        conversation_id=f"web:{tenant_id}:{visitor_id}",
        reply_text="Crash boundary",
        idempotency_key=idem,
        widget_key=widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    assert recovered.status == "delivered"
    assert recovered.billing_captured is True

    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 1
    assert session.pending_assistant[0].id == idem
    persist_mock.assert_awaited_once()

    final = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert final.reserved == 0
    assert final.ops.get("capture", 0) == 1
    assert final.ops.get("release", 0) == 0
