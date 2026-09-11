"""Continuation of Website Chat delivery-blocker acceptance tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.web_chat.operation_fsm import OperationState
from services.web_chat.persistence import PersistFailure, PersistOutcome, PersistResult
from services.web_chat.processor import WebChatError, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_chat_acceptance_fsm import _widget_and_visitor
from tests.web_chat_acceptance_billing import (
    assert_acceptance_ledger_equation,
    assert_pg_reservation_terminal,
    fetch_pg_ledger_snapshot,
)
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_ai_reply,
    patch_web_chat_store,
)


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
