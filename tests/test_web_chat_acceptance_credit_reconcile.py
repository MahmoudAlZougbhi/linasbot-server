"""PostgreSQL credit reconciliation: billing_pending + reserve idempotency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest

from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle
from services.web_chat.operation import (
    OperationRuntime,
    advance_operation,
    begin_operation,
    build_turn_payload,
    ensure_operation_credit_reserved,
    reconcile_billing_pending,
)
from services.web_chat.operation_fsm import OperationState, VerifiedSessionSnapshot
from services.web_chat.processor import WebChatError, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
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


def _expire_operation_lease(tenant_id: str, operation_key: str) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from services.web_chat.operation import operation_session
    from services.web_chat.pg_models import WebChatOperationRow

    with operation_session() as db:
        row = db.scalars(
            select(WebChatOperationRow).where(
                WebChatOperationRow.tenant_id == tenant_id,
                WebChatOperationRow.operation_key == operation_key,
            )
        ).first()
        assert row is not None
        row.lease_expires_at = datetime(2000, 1, 1, tzinfo=UTC)


def _snapshot(tenant_id: str = "biz", session_id: str = "visitor-reconcile") -> VerifiedSessionSnapshot:
    return VerifiedSessionSnapshot(
        tenant_id=tenant_id,
        widget_key="wk-reconcile",
        session_id=session_id,
        authority_hash="hash",
    )


def test_pg_reserve_idempotent_by_request_id(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path, tenant_id="biz")
    from services.credit_ledger_service import credit_ledger_service

    first = credit_ledger_service.reserve(
        tenant_id="biz",
        user_id=None,
        credits=1,
        operation_type="web_customer_reply",
        request_id="web:biz:idem-reserve",
    )
    second = credit_ledger_service.reserve(
        tenant_id="biz",
        user_id=None,
        credits=1,
        operation_type="web_customer_reply",
        request_id="web:biz:idem-reserve",
    )
    assert first == second
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz")
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )


def test_billing_pending_idle_handle_reconciles_one_capture(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """ACK-loss replay must capture once; visible delivery never releases."""
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    tenant_id = "biz"
    operation_key = "visitor-reconcile:turn-1"
    request_id = f"web:visitor-reconcile:{operation_key}"
    payload = build_turn_payload(session_id="visitor-reconcile", content="Hi")
    runtime = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=_snapshot(),
    )
    credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=None,
        request_id=request_id,
        operation_state=OperationState.CLAIMED,
    )
    ensure_operation_credit_reserved(runtime, credit)
    advance_operation(runtime, OperationState.REPLY_READY, result={"reply_text": "Visible"})
    advance_operation(runtime, OperationState.DURABLE_VISIBLE, result={"reply_text": "Visible"})
    advance_operation(
        runtime,
        OperationState.BILLING_PENDING,
        result={"reply_text": "Visible"},
        reservation_id=credit.reservation_id,
    )
    reservation_id = credit.reservation_id
    assert reservation_id

    replay_credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        request_id=request_id,
        operation_state=OperationState.BILLING_PENDING,
    )
    assert replay_credit.state == CreditFsmState.BILLING_PENDING
    record = reconcile_billing_pending(
        tenant_id=tenant_id,
        operation_key=operation_key,
        credit=replay_credit,
    )
    assert record is not None
    assert record.state == OperationState.COMPLETE
    assert replay_credit.state == CreditFsmState.CAPTURED

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "reserve": 1},
        captured=1,
    )
    assert_pg_reservation_terminal(acceptance_pg_ha_env, tenant_id, reservation_id, terminal="capture")


def test_reserve_retry_converges_after_crash_before_operation_reserved(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    tenant_id = "biz"
    operation_key = "visitor-crash:turn-1"
    request_id = f"web:visitor-crash:{operation_key}"
    payload = build_turn_payload(session_id="visitor-crash", content="Hi")
    begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=_snapshot(session_id="visitor-crash"),
    )
    credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=None,
        request_id=request_id,
        operation_state=OperationState.CLAIMED,
    )
    credit.reserve()
    assert credit.reservation_id
    reservation_id = credit.reservation_id
    _expire_operation_lease(tenant_id, operation_key)

    retry_runtime = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=_snapshot(session_id="visitor-crash"),
    )
    retry_credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=None,
        request_id=request_id,
        operation_state=OperationState.CLAIMED,
    )
    ensure_operation_credit_reserved(retry_runtime, retry_credit)
    assert retry_credit.reservation_id == reservation_id

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )


def test_reserve_retry_converges_after_fault_before_operation_commit(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    tenant_id = "biz"
    operation_key = "visitor-fault:turn-1"
    request_id = f"web:visitor-fault:{operation_key}"
    payload = build_turn_payload(session_id="visitor-fault", content="Hi")
    runtime = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=_snapshot(session_id="visitor-fault"),
    )
    credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=None,
        request_id=request_id,
        operation_state=OperationState.CLAIMED,
    )

    calls = 0
    original_advance = advance_operation

    def fault_once(runtime_obj: OperationRuntime, target: OperationState, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1 and target == OperationState.RESERVED:
            raise RuntimeError("crash before operation RESERVED commit")
        return original_advance(runtime_obj, target, **kwargs)

    monkeypatch.setattr("services.web_chat.operation_billing.advance_operation", fault_once)
    with pytest.raises(RuntimeError, match="crash before operation RESERVED"):
        ensure_operation_credit_reserved(runtime, credit)

    _expire_operation_lease(tenant_id, operation_key)
    retry_runtime = begin_operation(
        tenant_id=tenant_id,
        operation_key=operation_key,
        payload=payload,
        snapshot=_snapshot(session_id="visitor-fault"),
    )
    retry_credit = WebChatCreditHandle(
        tenant_id=tenant_id,
        reservation_id=None,
        request_id=request_id,
        operation_state=OperationState.CLAIMED,
    )
    ensure_operation_credit_reserved(retry_runtime, retry_credit)
    assert retry_credit.reservation_id == credit.reservation_id

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )


@pytest.mark.asyncio
async def test_capture_failure_replay_reconciles_without_release(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Visible reply + capture ACK loss must converge to one capture, never release."""
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor = store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    patch_ai_reply(monkeypatch, reply="Visible reply")
    calls = {"capture": 0}
    from services.credit_ledger_service import credit_ledger_service

    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id="conv",
            )
        ),
    )
    original_capture = credit_ledger_service.capture

    def fail_once_capture(**kwargs):
        calls["capture"] += 1
        if calls["capture"] == 1:
            raise RuntimeError("capture ack lost")
        return original_capture(**kwargs)

    monkeypatch.setattr(credit_ledger_service, "capture", fail_once_capture)

    with pytest.raises(WebChatError) as exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key="capture-ack-loss",
        )
    assert exc.value.code == "credit_capture_failed"

    mid = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert mid.reserved == 1
    assert mid.ops.get("release", 0) == 0

    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Hi",
        store=store,
        idempotency_key="capture-ack-loss",
    )
    assert reply == "Visible reply"

    final = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        final,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "reserve": 1},
        captured=1,
    )
    assert final.ops.get("release", 0) == 0


def test_pg_reserve_fifty_concurrent_same_request_id(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Direct 50-way reserve must converge: one reservation, zero IntegrityError."""
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path, tenant_id="biz")
    from services.credit_ledger_service import credit_ledger_service

    request_id = "web:biz:concurrent-reserve-50"
    errors: list[BaseException] = []

    def reserve_once() -> str:
        try:
            return credit_ledger_service.reserve(
                tenant_id="biz",
                user_id=None,
                credits=1,
                operation_type="web_customer_reply",
                request_id=request_id,
            )
        except BaseException as exc:
            errors.append(exc)
            raise

    with ThreadPoolExecutor(max_workers=50) as pool:
        reservation_ids = list(pool.map(lambda _: reserve_once(), range(50)))

    assert not errors
    assert len(set(reservation_ids)) == 1
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz")
    assert snapshot.ops.get("reserve", 0) == 1
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )
