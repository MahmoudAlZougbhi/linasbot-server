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


def release_web_chat_message_hold(
    *,
    tenant_id: str,
    operation_key: str,
    conversation_id: str = "",
    user_text: str = "",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> None:
    """Release a never-submitted Website Chat message hold. Do not invent conversation or text."""
    from services.customer_ai.billing import settle_after_send
    from services.customer_ai.history_ids import web_inbound_message_id

    cid = str(conversation_id or "").strip()
    text = str(user_text or "").strip()
    web_mid = web_inbound_message_id(cid, text) if cid and text else ""
    settle_after_send(
        tenant_id=tenant_id,
        operation_id=web_mid or operation_key,
        accepted=False,
        channel="web_chat",
        extra_ids=(operation_key, web_mid, *extra_ids),
    )


def fenced_failure_release(
    runtime: OperationRuntime,
    credit: Any,
    *,
    conversation_id: str = "",
    user_text: str = "",
) -> bool:
    """Release reservation and mark RELEASED only when owner+generation still match."""
    released = False
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
            released = True
        elif current == OperationState.RELEASE_PENDING:
            return False
        elif current == OperationState.CLAIMED and not row.reservation_id and not credit.reservation_id:
            return False
        elif not may_release_credit(current):
            return False
        else:
            leftover_ok = credit.reconcile_release()
            if not leftover_ok:
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
            released = True
    if released:
        result = getattr(runtime.record, "result", None) or {}
        release_web_chat_message_hold(
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            conversation_id=conversation_id or str(result.get("conversation_id") or ""),
            user_text=user_text,
            extra_ids=(str(result.get("operation_key") or ""), conversation_id),
        )
    return released
