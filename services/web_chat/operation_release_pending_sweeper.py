"""Bounded production reconciler for durable RELEASE_PENDING operations."""

from __future__ import annotations

from dataclasses import dataclass

from services.web_chat.credit_fsm import WebChatCreditHandle
from services.web_chat.operation import (
    OperationRuntime,
    _get_row,
    _row_to_record,
    advance_operation,
    new_lease_owner,
    operation_session,
)
from services.web_chat.operation_credit_reconcile import list_release_pending_operations
from services.web_chat.operation_fsm import OperationRecord, OperationState
from services.web_chat.operation_lease import handoff_lease, lease_active


@dataclass(frozen=True)
class ReleasePendingSweepResult:
    examined: int
    released: int
    pending: int
    skipped: int
    failed: int


def _claim_release_pending_row(
    *,
    tenant_id: str,
    operation_key: str,
    lease_owner: str,
) -> OperationRecord | None:
    with operation_session() as db:
        row = _get_row(db, tenant_id=tenant_id, operation_key=operation_key, for_update=True)
        if row is None:
            return None
        current = OperationState(str(row.state))
        if current != OperationState.RELEASE_PENDING:
            return _row_to_record(row)
        if lease_active(row) and row.lease_owner != lease_owner:
            return None
        if not lease_active(row):
            handoff_lease(row, lease_owner=lease_owner)
        db.flush()
        return _row_to_record(row)


def reconcile_release_pending_operation(
    record: OperationRecord,
    *,
    lease_owner: str,
) -> str:
    """Reconcile one RELEASE_PENDING row; never run AI or visible side effects."""
    from services.credit_ledger_service import credit_ledger_service

    claimed = _claim_release_pending_row(
        tenant_id=record.tenant_id,
        operation_key=record.operation_key,
        lease_owner=lease_owner,
    )
    if claimed is None:
        return "skipped_active_lease"
    if claimed.state != OperationState.RELEASE_PENDING:
        return "already_resolved"
    if not claimed.reservation_id:
        return "failed"

    runtime = OperationRuntime(
        tenant_id=claimed.tenant_id,
        operation_key=claimed.operation_key,
        lease_owner=lease_owner,
        lease_generation=int(claimed.lease_generation or 1),
        record=claimed,
    )
    credit = WebChatCreditHandle(
        tenant_id=claimed.tenant_id,
        reservation_id=claimed.reservation_id,
        request_id=f"web:sweep:{claimed.operation_key}",
        operation_state=OperationState.RELEASE_PENDING,
    )
    terminal = credit_ledger_service.reservation_terminal(claimed.tenant_id, claimed.reservation_id)
    if terminal == "capture":
        return "failed"
    if terminal == "release":
        advance_operation(runtime, OperationState.RELEASED, released=True)
        return "released"
    if terminal is None:
        if credit.reconcile_release():
            advance_operation(runtime, OperationState.RELEASED, released=True)
            return "released"
        return "pending"
    return "failed"


def sweep_release_pending_operations(*, limit: int = 50) -> ReleasePendingSweepResult:
    """Discover and reconcile RELEASE_PENDING operations without customer retries."""
    lease_owner = new_lease_owner()
    pending = list_release_pending_operations(limit=limit)
    released = pending_count = skipped = failed = 0
    for record in pending:
        try:
            outcome = reconcile_release_pending_operation(record, lease_owner=lease_owner)
        except Exception:
            failed += 1
            continue
        if outcome == "released":
            released += 1
        elif outcome == "pending":
            pending_count += 1
        elif outcome == "skipped_active_lease":
            skipped += 1
        elif outcome == "failed":
            failed += 1
    return ReleasePendingSweepResult(
        examined=len(pending),
        released=released,
        pending=pending_count,
        skipped=skipped,
        failed=failed,
    )
