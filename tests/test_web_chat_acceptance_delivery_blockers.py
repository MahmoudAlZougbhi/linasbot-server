"""Acceptance tests for delivery blockers: cross-tenant, recovery, release, projection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
from services.smart_followup.adapters.web import WebFollowUpAdapter
from services.smart_followup.types import FollowUpConversationView
from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle
from services.web_chat.followup_delivery import deliver_web_followup_message
from services.web_chat.operation_fsm import OperationFsmError, OperationState
from services.web_chat.persistence import PersistFailure, PersistOutcome, PersistResult
from services.web_chat.processor import WebChatError, compose_web_user_id, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_chat_acceptance_fsm import _widget_and_visitor
from tests.test_web_followup_web_delivery import _reserve_followup_credit
from tests.web_chat_acceptance_billing import (
    assert_acceptance_ledger_equation,
    assert_pg_reservation_terminal,
    fetch_pg_ledger_snapshot,
)
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_ai_reply,
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


@pytest.mark.asyncio
async def test_unresolved_release_failure_blocks_second_reserve_until_confirmed(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """Release ACK loss must keep reservation authority until release is confirmed."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    from services.credit_ledger_service import credit_ledger_service
    from tests.test_web_chat_operation_lease_fence import _operation_snapshot

    release_calls = 0
    original_release = credit_ledger_service.release

    def fail_once_release(**kwargs):
        nonlocal release_calls
        release_calls += 1
        if release_calls == 1:
            raise RuntimeError("release ack lost")
        return original_release(**kwargs)

    monkeypatch.setattr(credit_ledger_service, "release", fail_once_release)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=RuntimeError("ai down")),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv"),
        ),
    )

    idem = "release-fail-retry-key"
    operation_key = f"{visitor.id}:{idem}"
    with pytest.raises(WebChatError) as first_exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key=idem,
        )
    assert first_exc.value.code == "ai_failed"

    first_row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert first_row["state"] == OperationState.RELEASE_PENDING.value
    assert first_row["released"] is False
    first_reservation_id = first_row["reservation_id"]
    assert first_reservation_id

    first_ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert first_ledger.ops.get("reserve", 0) == 1
    assert first_ledger.ops.get("release", 0) == 0
    assert first_ledger.reserved == 1

    from tests.test_web_chat_operation_lease_fence import _expire_operation_lease

    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)

    with pytest.raises(WebChatError) as second_exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key=idem,
        )
    assert second_exc.value.code == "ai_failed"

    second_row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert second_row["state"] == OperationState.RELEASED.value
    assert second_row["released"] is True
    mid_ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert mid_ledger.ops.get("reserve", 0) == 2
    assert mid_ledger.ops.get("release", 0) == 2
    assert mid_ledger.reserved == 0

    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)
    patch_ai_reply(monkeypatch, reply="Recovered after release")
    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Hi",
        store=store,
        idempotency_key=idem,
    )
    assert reply == "Recovered after release"
    session = store.get_visitor(visitor.id)
    assert session is not None
    assert any(msg.role == "assistant" and msg.content == "Recovered after release" for msg in session.messages)

    final_ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        final_ledger,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "release": 2, "reserve": 3},
        captured=1,
    )
    assert_pg_reservation_terminal(acceptance_pg_ha_env, tenant_id, first_reservation_id, terminal="release")


@pytest.mark.asyncio
async def test_release_ack_loss_after_commit_converges_before_ai(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Committed release with post-commit throw must reconcile before AI on retry."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    from services.credit_ledger_service import credit_ledger_service
    from services.web_chat.operation_credit_reconcile import list_release_pending_operations
    from tests.test_web_chat_operation_lease_fence import _expire_operation_lease, _operation_snapshot

    original_release = credit_ledger_service.release
    ai_calls = 0
    persist_calls = 0
    first_attempt = True

    def commit_then_throw_release(**kwargs):
        original_release(**kwargs)
        raise RuntimeError("release ack lost after commit")

    async def ai_fail_first_then_success_after_reconcile(**_kwargs):
        nonlocal ai_calls, first_attempt
        row = _operation_snapshot(
            tenant_id=tenant_id,
            operation_key=f"{visitor.id}:release-ack-loss-key",
        )
        if row["state"] == OperationState.RELEASE_PENDING.value:
            raise AssertionError("AI invoked before release reconciliation")
        ai_calls += 1
        if first_attempt:
            first_attempt = False
            raise RuntimeError("ai down")
        from types import SimpleNamespace

        return SimpleNamespace(reply="Paid reply")

    async def track_persist(*_args, **_kwargs):
        nonlocal persist_calls
        persist_calls += 1
        return PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv")

    monkeypatch.setattr(credit_ledger_service, "release", commit_then_throw_release)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        ai_fail_first_then_success_after_reconcile,
    )
    monkeypatch.setattr("services.web_chat.processor.persist_web_chat_message", track_persist)

    idem = "release-ack-loss-key"
    operation_key = f"{visitor.id}:{idem}"
    with pytest.raises(WebChatError) as first_exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key=idem,
        )
    assert first_exc.value.code == "ai_failed"

    first_row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert first_row["state"] == OperationState.RELEASE_PENDING.value
    first_reservation_id = first_row["reservation_id"]
    assert first_reservation_id
    pending = list_release_pending_operations(tenant_id=tenant_id)
    assert any(row.operation_key == operation_key for row in pending)

    first_ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert first_ledger.ops.get("reserve", 0) == 1
    assert first_ledger.ops.get("release", 0) == 1
    assert first_ledger.reserved == 0
    assert persist_calls == 0

    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)
    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Hi",
        store=store,
        idempotency_key=idem,
    )
    assert reply == "Paid reply"
    assert ai_calls == 2
    assert persist_calls >= 1

    second_row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert second_row["state"] != OperationState.RELEASE_PENDING.value
    assert_pg_reservation_terminal(acceptance_pg_ha_env, tenant_id, first_reservation_id, terminal="release")

    session = store.get_visitor(visitor.id)
    assert session is not None
    assert any(msg.role == "assistant" and msg.content == "Paid reply" for msg in session.messages)

    final_ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        final_ledger,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "release": 1, "reserve": 2},
        captured=1,
    )


@pytest.mark.asyncio
async def test_firestore_skip_is_not_duplicate(tmp_path, monkeypatch) -> None:
    from services.web_chat.persistence import persist_web_chat_message
    from utils.conversation_save_result import FirestoreSaveOutcome, FirestoreSaveStatus

    monkeypatch.setattr(
        "services.web_chat.persistence.save_conversation_message_to_firestore",
        AsyncMock(return_value=FirestoreSaveOutcome(status=FirestoreSaveStatus.SKIPPED, conversation_id="c1")),
    )
    with pytest.raises(PersistFailure, match="unavailable"):
        await persist_web_chat_message(
            user_id="u1",
            role="ai",
            text="Hi",
            conversation_id="c1",
            metadata={"source_message_id": "m1"},
        )
