"""Real-PG tests for RELEASE_PENDING edges and production sweeper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.web_chat.operation_fsm import OperationState
from services.web_chat.operation_release_pending_sweeper import (
    reconcile_release_pending_operation,
    sweep_release_pending_operations,
)
from services.web_chat.processor import WebChatError, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_chat_acceptance_fsm import _widget_and_visitor
from tests.test_web_chat_operation_lease_fence import _expire_operation_lease, _operation_snapshot
from tests.web_chat_acceptance_billing import fetch_pg_ledger_snapshot
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_ai_reply,
    patch_web_chat_store,
)


@pytest.mark.asyncio
async def test_reply_ready_persist_failure_commit_throw_stays_pending_without_visible_reply(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    from services.credit_ledger_service import credit_ledger_service

    original_release = credit_ledger_service.release

    def commit_then_throw_release(**kwargs):
        original_release(**kwargs)
        raise RuntimeError("release ack lost after persist failure")

    monkeypatch.setattr(credit_ledger_service, "release", commit_then_throw_release)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    patch_ai_reply(monkeypatch, reply="Ready but not durable")
    monkeypatch.setattr(
        "services.web_chat.processor_completion._persist_web_turn",
        AsyncMock(side_effect=WebChatError("persist_failed", "Could not persist.", status_code=503)),
    )

    idem = "reply-ready-persist-fail"
    operation_key = f"{visitor.id}:{idem}"
    with pytest.raises(WebChatError):
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key=idem,
        )

    row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row["state"] == OperationState.RELEASE_PENDING.value
    session = store.get_visitor(visitor.id)
    assert session is not None
    assert not any(msg.content == "Ready but not durable" for msg in session.messages)
    assert len(session.pending_assistant) == 0

    ledger = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert ledger.ops.get("release", 0) == 1
    assert ledger.reserved == 0


@pytest.mark.asyncio
async def test_claimed_without_reservation_returns_402_not_fsm_error(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)

    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    from services.credit_ledger_service import credit_ledger_service

    monkeypatch.setattr(
        credit_ledger_service,
        "reserve",
        lambda **_kwargs: (_ for _ in ()).throw(PermissionError("insufficient")),
    )

    with pytest.raises(WebChatError) as exc_info:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key="claimed-no-reservation",
        )
    assert exc_info.value.code == "insufficient_credits"
    assert exc_info.value.status_code == 402


@pytest.mark.asyncio
async def test_sweeper_converges_committed_ack_loss_without_customer_retry(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)
    tenant_id = widget.tenant_id
    from services.credit_ledger_service import credit_ledger_service

    original_release = credit_ledger_service.release

    def commit_then_throw_release(**kwargs):
        original_release(**kwargs)
        raise RuntimeError("release ack lost after persist failure")

    monkeypatch.setattr(credit_ledger_service, "release", commit_then_throw_release)
    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    patch_ai_reply(monkeypatch, reply="Sweeper target")
    monkeypatch.setattr(
        "services.web_chat.processor_completion._persist_web_turn",
        AsyncMock(side_effect=WebChatError("persist_failed", "Could not persist.", status_code=503)),
    )

    idem = "sweeper-ack-loss"
    operation_key = f"{visitor.id}:{idem}"
    with pytest.raises(WebChatError):
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key=idem,
        )

    _expire_operation_lease(tenant_id=tenant_id, operation_key=operation_key)
    result = sweep_release_pending_operations(limit=10)
    assert result.released >= 1

    row = _operation_snapshot(tenant_id=tenant_id, operation_key=operation_key)
    assert row["state"] == OperationState.RELEASED.value
    assert row["released"] is True


def test_reconcile_skips_when_foreign_lease_is_active(monkeypatch) -> None:
    from services.web_chat.operation_fsm import OperationRecord, OperationState, VerifiedSessionSnapshot

    record = OperationRecord(
        tenant_id="biz",
        operation_key="visitor:foreign-lease",
        payload_hash="hash",
        state=OperationState.RELEASE_PENDING,
        attempt=1,
        lease_owner="foreign-owner",
        reservation_id="res-1",
        result=None,
        snapshot=VerifiedSessionSnapshot("biz", "wk", "visitor", "auth"),
        lease_generation=2,
        released=False,
    )
    monkeypatch.setattr(
        "services.web_chat.operation_release_pending_sweeper._claim_release_pending_row",
        lambda **_kwargs: None,
    )
    assert reconcile_release_pending_operation(record, lease_owner="sweeper-owner") == "skipped_active_lease"
