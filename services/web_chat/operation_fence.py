"""Fenced external effects — stale workers cannot mutate durable operation state."""

from __future__ import annotations

from typing import Any

from services.web_chat.operation import (
    OperationRuntime,
    _get_row,
    _row_to_record,
    _sync_runtime_lease,
    operation_session,
)
from services.web_chat.operation_fsm import OperationFsmError, OperationState, assert_transition, may_release_credit
from services.web_chat.operation_lease import assert_lease_fence, extend_lease


def fenced_failure_release(runtime: OperationRuntime, credit: Any) -> bool:
    """Release reservation and mark RELEASED only when owner+generation still match."""
    with operation_session() as db:
        row = _get_row(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            for_update=True,
        )
        if row is None:
            return False
        try:
            assert_lease_fence(row, lease_owner=runtime.lease_owner, lease_generation=runtime.lease_generation)
        except OperationFsmError as exc:
            if exc.code == "lease_fence_stale":
                return False
            raise
        current = OperationState(str(row.state))
        if current == OperationState.RELEASED:
            record = _row_to_record(row)
            _sync_runtime_lease(runtime, record)
            return True
        if current == OperationState.RELEASE_PENDING:
            return False
        if current == OperationState.CLAIMED and not row.reservation_id and not credit.reservation_id:
            return False
        if not may_release_credit(current):
            return False
        released = credit.reconcile_release()
        if not released:
            if credit.reservation_id:
                row.reservation_id = credit.reservation_id
            row.released = False
            if current != OperationState.RELEASE_PENDING:
                assert_transition(row.state, OperationState.RELEASE_PENDING)
                row.state = OperationState.RELEASE_PENDING.value
            extend_lease(row)
            db.flush()
            record = _row_to_record(row)
            _sync_runtime_lease(runtime, record)
            return False
        row.reservation_id = None
        assert_transition(row.state, OperationState.RELEASED)
        row.state = OperationState.RELEASED.value
        row.released = True
        extend_lease(row)
        db.flush()
        record = _row_to_record(row)
    _sync_runtime_lease(runtime, record)
    return True
