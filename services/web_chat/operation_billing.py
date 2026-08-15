"""Billing reconciliation helpers for durable web-chat operations."""

from __future__ import annotations

from typing import Any

from services.web_chat.operation import (
    OperationRuntime,
    advance_operation,
    operation_session,
    web_chat_operation_repository,
)
from services.web_chat.operation_fsm import OperationFsmError, OperationRecord, OperationState, is_terminal_state


def reconcile_billing_pending(
    *,
    tenant_id: str,
    operation_key: str,
    credit: Any,
    model_provider: str = "web_chat",
) -> OperationRecord | None:
    with operation_session() as db:
        record = web_chat_operation_repository.get(db, tenant_id=tenant_id, operation_key=operation_key)
        if record is None or record.state not in {
            OperationState.BILLING_PENDING,
            OperationState.DURABLE_VISIBLE,
        }:
            return record
        if not record.reservation_id:
            return record
        credit.reservation_id = record.reservation_id
        credit.operation_state = record.state
        credit.hydrate_from_operation_context()
        if not credit.reconcile_capture(model_provider=model_provider):
            return record
        captured = web_chat_operation_repository.system_reclaim_transition(
            db,
            tenant_id=tenant_id,
            operation_key=operation_key,
            target=OperationState.CAPTURED,
            result=record.result,
        )
        if captured.state != OperationState.CAPTURED:
            return captured
        return web_chat_operation_repository.system_reclaim_transition(
            db,
            tenant_id=tenant_id,
            operation_key=operation_key,
            target=OperationState.COMPLETE,
            result=captured.result,
        )


def ensure_operation_credit_reserved(
    runtime: OperationRuntime,
    credit: Any,
) -> OperationRecord:
    """Converge ledger reservation with operation RESERVED without double-reserve."""
    from services.web_chat.credit_fsm import CreditFsmState

    credit.hydrate_from_operation_context()
    record = runtime.record
    if record is not None and record.reservation_id:
        credit.reservation_id = record.reservation_id
        credit.operation_state = record.state
        credit.state = CreditFsmState.RESERVED
        if record.state in {OperationState.RESERVED, OperationState.REPLY_READY, OperationState.BILLING_PENDING}:
            return record
    if record is not None and record.state == OperationState.RELEASE_PENDING:
        raise OperationFsmError("release_pending", "Credit release is pending reconciliation.")

    existing = credit.reconcile_existing_reservation()
    if existing:
        credit.reservation_id = existing
        credit.state = CreditFsmState.RESERVED
        if record is None or record.state == OperationState.CLAIMED:
            return advance_operation(
                runtime,
                OperationState.RESERVED,
                reservation_id=existing,
            )
        return record

    if record is not None and record.state != OperationState.CLAIMED:
        return record

    if credit.state == CreditFsmState.RELEASE_PENDING:
        if credit.reservation_id and not credit.reconcile_release():
            assert record is not None
            return record

    credit.reserve()
    return advance_operation(runtime, OperationState.RESERVED, reservation_id=credit.reservation_id)


def mark_operation_delivery_acked(
    *,
    tenant_id: str,
    operation_key: str,
) -> OperationRecord | None:
    """Browser delivery ACK — never skip billing; only complete when capture is proven."""
    with operation_session() as db:
        record = web_chat_operation_repository.get(db, tenant_id=tenant_id, operation_key=operation_key)
        if record is None:
            return None
        if is_terminal_state(record.state):
            return record
        if record.state != OperationState.CAPTURED:
            return record
        completed = web_chat_operation_repository.system_reclaim_transition(
            db,
            tenant_id=tenant_id,
            operation_key=operation_key,
            target=OperationState.COMPLETE,
            result=record.result,
        )
        if completed.state == OperationState.COMPLETE:
            return completed
    return record


def mark_operation_complete_for_ack(
    *,
    tenant_id: str,
    operation_key: str,
) -> OperationRecord | None:
    """Backward-compatible alias — delivery ACK must not bypass billing."""
    return mark_operation_delivery_acked(tenant_id=tenant_id, operation_key=operation_key)
