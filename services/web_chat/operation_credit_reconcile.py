"""Reconcile ledger credit authority before AI, persistence, or outbox side effects."""

from __future__ import annotations

from typing import Any

from services.web_chat.operation import (
    OperationRuntime,
    advance_operation,
    operation_session,
    refresh_operation_runtime,
)
from services.web_chat.operation_fsm import OperationFsmError, OperationRecord, OperationState
from services.web_chat.pg_models import WebChatOperationRow


def _reclaim_released_attempt(runtime: OperationRuntime) -> OperationRecord:
    from services.web_chat.operation import _get_row, _row_to_record
    from services.web_chat.operation_lease import handoff_lease

    with operation_session() as db:
        row = _get_row(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            for_update=True,
        )
        if row is None:
            raise OperationFsmError("operation_missing", "Operation not found.")
        if OperationState(str(row.state)) != OperationState.RELEASED:
            raise OperationFsmError("release_pending", "Released reclaim requires RELEASED state.")
        row.state = OperationState.CLAIMED.value
        row.released = False
        row.reservation_id = None
        row.result = None
        row.attempt = int(row.attempt or 1) + 1
        handoff_lease(row, lease_owner=runtime.lease_owner)
        db.flush()
        record = _row_to_record(row)
    runtime.record = record
    runtime.lease_generation = int(record.lease_generation or 1)
    return record


def _reset_credit_for_reclaimed_attempt(credit: Any, *, record: OperationRecord) -> None:
    from services.web_chat.credit_fsm import CreditFsmState

    credit.reservation_id = None
    credit.operation_state = record.state
    credit.state = CreditFsmState.IDLE
    credit.hydrate_from_operation_context()


def _converge_terminal_release(runtime: OperationRuntime, credit: Any, *, record: OperationRecord) -> OperationRecord:
    advance_operation(runtime, OperationState.RELEASED, released=True)
    credit.reservation_id = None
    credit.operation_state = OperationState.RELEASED
    reclaimed = _reclaim_released_attempt(runtime)
    _reset_credit_for_reclaimed_attempt(credit, record=reclaimed)
    return reclaimed


def reconcile_credit_before_side_effects(runtime: OperationRuntime, credit: Any) -> OperationRecord | None:
    """Fail closed until release-pending/terminal release is reconciled; never run AI first."""
    from services.credit_ledger_service import credit_ledger_service

    refresh_operation_runtime(runtime)
    record = runtime.record
    if record is None:
        return None

    if record.state == OperationState.RELEASE_PENDING:
        if not record.reservation_id:
            raise OperationFsmError("release_pending", "Release pending without reservation authority.")
        credit.reservation_id = record.reservation_id
        credit.operation_state = record.state
        credit.hydrate_from_operation_context()
        terminal = credit_ledger_service.reservation_terminal(record.tenant_id, record.reservation_id)
        if terminal == "release":
            return _converge_terminal_release(runtime, credit, record=record)
        if terminal == "capture":
            raise OperationFsmError("release_pending", "Reservation terminal is inconsistent for release pending.")
        if terminal is None:
            if not credit.reconcile_release():
                raise OperationFsmError("release_pending", "Credit release is pending reconciliation.")
            return _converge_terminal_release(runtime, credit, record=record)
        raise OperationFsmError("release_pending", "Unknown reservation terminal during release pending.")

    if record.reservation_id and record.state in {
        OperationState.RESERVED,
        OperationState.CLAIMED,
        OperationState.REPLY_READY,
    }:
        terminal = credit_ledger_service.reservation_terminal(record.tenant_id, record.reservation_id)
        if terminal == "release":
            credit.reservation_id = record.reservation_id
            credit.operation_state = record.state
            return _converge_terminal_release(runtime, credit, record=record)

    return record


def list_release_pending_operations(*, tenant_id: str | None = None, limit: int = 50) -> list[OperationRecord]:
    from sqlalchemy import select

    from services.web_chat.operation import _row_to_record

    with operation_session() as db:
        query = select(WebChatOperationRow).where(
            WebChatOperationRow.state == OperationState.RELEASE_PENDING.value,
        )
        if tenant_id is not None:
            query = query.where(WebChatOperationRow.tenant_id == tenant_id)
        rows = db.scalars(query.order_by(WebChatOperationRow.updated_at.asc()).limit(limit)).all()
        return [_row_to_record(row) for row in rows]
