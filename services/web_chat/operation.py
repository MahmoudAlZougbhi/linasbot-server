"""PostgreSQL persistence and orchestration for Website Chat operations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services.web_chat.ha_repository import WebChatHaUnavailable, with_ha_session
from services.web_chat.operation_fsm import (
    OperationFsmError,
    OperationRecord,
    OperationState,
    VerifiedSessionSnapshot,
    assert_transition,
    canonical_payload_hash,
    is_terminal_state,
)
from services.web_chat.operation_lease import (
    LEASE_TTL_SECONDS,
    assert_lease_fence,
    extend_lease,
    handoff_lease,
    lease_active,
    lease_generation_of,
)
from services.web_chat.pg_models import WebChatOperationRow

ClaimStatus = Literal["created", "replay", "resume", "conflict", "in_progress"]


@dataclass(frozen=True)
class OperationClaimResult:
    status: ClaimStatus
    record: OperationRecord | None = None
    message: str = ""


def _now() -> datetime:
    return datetime.now(UTC)


def _lease_ttl_seconds() -> int:
    return LEASE_TTL_SECONDS


def _row_to_record(row: WebChatOperationRow) -> OperationRecord:
    return OperationRecord(
        tenant_id=row.tenant_id,
        operation_key=row.operation_key,
        payload_hash=row.payload_hash,
        state=OperationState(row.state),
        attempt=int(row.attempt or 1),
        lease_owner=str(row.lease_owner or ""),
        lease_generation=lease_generation_of(row),
        reservation_id=row.reservation_id,
        result=dict(row.result or {}) if row.result else None,
        snapshot=VerifiedSessionSnapshot.from_dict(row.snapshot),
        released=bool(row.released),
    )


def _get_row(
    session: Session,
    *,
    tenant_id: str,
    operation_key: str,
    for_update: bool = False,
) -> WebChatOperationRow | None:
    stmt = select(WebChatOperationRow).where(
        WebChatOperationRow.tenant_id == tenant_id,
        WebChatOperationRow.operation_key == operation_key,
    )
    if for_update:
        stmt = stmt.with_for_update()
    return session.scalars(stmt).first()


class WebChatOperationRepository:
    def claim(
        self,
        session: Session,
        *,
        tenant_id: str,
        operation_key: str,
        payload: dict[str, Any],
        snapshot: VerifiedSessionSnapshot,
        lease_owner: str,
    ) -> OperationClaimResult:
        payload_hash = canonical_payload_hash(payload)
        existing = _get_row(session, tenant_id=tenant_id, operation_key=operation_key, for_update=True)
        if existing is not None:
            result = self._evaluate_existing(existing, payload_hash=payload_hash, lease_owner=lease_owner)
            session.flush()
            return result

        row = WebChatOperationRow(
            tenant_id=tenant_id,
            session_id=snapshot.session_id,
            operation_key=operation_key,
            payload_hash=payload_hash,
            state=OperationState.CLAIMED.value,
            attempt=1,
            lease_owner=lease_owner,
            lease_generation=1,
            lease_expires_at=_now() + timedelta(seconds=_lease_ttl_seconds()),
            snapshot=snapshot.to_dict(),
        )
        session.add(row)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            raced = _get_row(session, tenant_id=tenant_id, operation_key=operation_key, for_update=True)
            if raced is None:
                raise WebChatHaUnavailable("Operation claim race could not be resolved.") from None
            return self._evaluate_existing(raced, payload_hash=payload_hash, lease_owner=lease_owner)
        return OperationClaimResult(status="created", record=_row_to_record(row))

    def _evaluate_existing(
        self,
        row: WebChatOperationRow,
        *,
        payload_hash: str,
        lease_owner: str,
    ) -> OperationClaimResult:
        if row.payload_hash != payload_hash:
            return OperationClaimResult(
                status="conflict",
                message="Operation key reused with mismatched payload.",
            )
        record = _row_to_record(row)
        if record.state == OperationState.RELEASE_PENDING:
            if not lease_active(row) or row.lease_owner != lease_owner:
                handoff_lease(row, lease_owner=lease_owner)
            return OperationClaimResult(status="resume", record=_row_to_record(row))
        if record.state == OperationState.RELEASED:
            if record.reservation_id:
                from services.credit_ledger_service import credit_ledger_service

                if credit_ledger_service.reservation_terminal(record.tenant_id, record.reservation_id) is None:
                    row.state = OperationState.RESERVED.value
                    row.released = False
                    handoff_lease(row, lease_owner=lease_owner)
                    return OperationClaimResult(status="resume", record=_row_to_record(row))
            if not record.released:
                row.state = OperationState.RESERVED.value if record.reservation_id else OperationState.CLAIMED.value
                row.released = False
                handoff_lease(row, lease_owner=lease_owner)
                return OperationClaimResult(status="resume", record=_row_to_record(row))
            row.state = OperationState.CLAIMED.value
            row.released = False
            row.reservation_id = None
            row.result = None
            row.attempt = int(row.attempt or 1) + 1
            handoff_lease(row, lease_owner=lease_owner)
            return OperationClaimResult(status="resume", record=_row_to_record(row))
        if is_terminal_state(record.state):
            return OperationClaimResult(status="replay", record=record)
        if record.state in {
            OperationState.DURABLE_VISIBLE,
            OperationState.CAPTURED,
            OperationState.BILLING_PENDING,
        }:
            if lease_active(row) and row.lease_owner != lease_owner:
                return OperationClaimResult(status="in_progress", record=record, message="Operation in progress.")
            if not lease_active(row):
                handoff_lease(row, lease_owner=lease_owner)
            return OperationClaimResult(status="resume", record=_row_to_record(row))
        if lease_active(row) and row.lease_owner != lease_owner:
            return OperationClaimResult(status="in_progress", record=record, message="Operation in progress.")
        if not lease_active(row):
            handoff_lease(row, lease_owner=lease_owner)
        return OperationClaimResult(status="resume", record=_row_to_record(row))

    def transition(
        self,
        session: Session,
        *,
        tenant_id: str,
        operation_key: str,
        target: OperationState,
        lease_owner: str,
        lease_generation: int,
        reservation_id: str | None = None,
        result: dict[str, Any] | None = None,
        released: bool | None = None,
    ) -> OperationRecord:
        row = _get_row(session, tenant_id=tenant_id, operation_key=operation_key, for_update=True)
        if row is None:
            raise OperationFsmError("operation_missing", "Operation not found.")
        current = OperationState(str(row.state))
        if current == target and target in {OperationState.CAPTURED, OperationState.COMPLETE}:
            return _row_to_record(row)
        if is_terminal_state(current):
            return _row_to_record(row)
        assert_lease_fence(row, lease_owner=lease_owner, lease_generation=lease_generation)
        assert_transition(row.state, target)
        row.state = target.value
        extend_lease(row)
        if reservation_id is not None:
            row.reservation_id = reservation_id
        if result is not None:
            row.result = dict(result)
        if released is not None:
            row.released = released
        if target == OperationState.RELEASED:
            row.reservation_id = None
        if target in {OperationState.RELEASED, OperationState.BILLING_PENDING, OperationState.COMPLETE}:
            row.attempt = int(row.attempt or 1)
        session.flush()
        return _row_to_record(row)

    def try_transition(
        self,
        session: Session,
        *,
        tenant_id: str,
        operation_key: str,
        from_state: OperationState,
        target: OperationState,
        lease_owner: str,
        lease_generation: int,
        reservation_id: str | None = None,
        result: dict[str, Any] | None = None,
        released: bool | None = None,
    ) -> tuple[OperationRecord | None, bool]:
        row = _get_row(session, tenant_id=tenant_id, operation_key=operation_key, for_update=True)
        if row is None:
            return None, False
        current = OperationState(str(row.state))
        if current != from_state:
            return _row_to_record(row), False
        try:
            assert_lease_fence(row, lease_owner=lease_owner, lease_generation=lease_generation)
        except OperationFsmError as exc:
            if exc.code == "lease_fence_stale":
                return _row_to_record(row), False
            raise
        assert_transition(row.state, target)
        row.state = target.value
        extend_lease(row)
        if reservation_id is not None:
            row.reservation_id = reservation_id
        if result is not None:
            row.result = dict(result)
        if released is not None:
            row.released = released
        if target == OperationState.RELEASED:
            row.reservation_id = None
        session.flush()
        return _row_to_record(row), True

    def get(self, session: Session, *, tenant_id: str, operation_key: str) -> OperationRecord | None:
        row = _get_row(session, tenant_id=tenant_id, operation_key=operation_key)
        return _row_to_record(row) if row is not None else None

    def system_reclaim_transition(
        self,
        session: Session,
        *,
        tenant_id: str,
        operation_key: str,
        target: OperationState,
        reservation_id: str | None = None,
        result: dict[str, Any] | None = None,
        released: bool | None = None,
    ) -> OperationRecord:
        """Reclaim an expired lease and transition in one locked transaction."""
        row = _get_row(session, tenant_id=tenant_id, operation_key=operation_key, for_update=True)
        if row is None:
            raise OperationFsmError("operation_missing", "Operation not found.")
        current = OperationState(str(row.state))
        if current == target:
            return _row_to_record(row)
        if is_terminal_state(current):
            return _row_to_record(row)
        handoff_lease(row, lease_owner=new_lease_owner())
        assert_transition(row.state, target)
        row.state = target.value
        extend_lease(row)
        if reservation_id is not None:
            row.reservation_id = reservation_id
        if result is not None:
            row.result = dict(result)
        if released is not None:
            row.released = released
        session.flush()
        return _row_to_record(row)

    def list_billing_pending(self, session: Session, *, tenant_id: str, limit: int = 50) -> list[OperationRecord]:
        rows = session.scalars(
            select(WebChatOperationRow)
            .where(
                WebChatOperationRow.tenant_id == tenant_id,
                WebChatOperationRow.state == OperationState.BILLING_PENDING.value,
            )
            .order_by(WebChatOperationRow.updated_at.asc())
            .limit(limit)
        ).all()
        return [_row_to_record(row) for row in rows]


web_chat_operation_repository = WebChatOperationRepository()


def new_lease_owner() -> str:
    return uuid.uuid4().hex


def build_turn_payload(*, session_id: str, content: str) -> dict[str, Any]:
    return {"kind": "visitor_turn", "session_id": session_id, "content": (content or "").strip()}


def build_followup_payload(*, visitor_id: str, reply_text: str, idempotency_key: str) -> dict[str, Any]:
    return {
        "kind": "followup",
        "visitor_id": visitor_id,
        "reply_text": (reply_text or "").strip(),
        "idempotency_key": idempotency_key,
    }


def operation_session() -> Any:
    return with_ha_session()


@dataclass
class OperationRuntime:
    tenant_id: str
    operation_key: str
    lease_owner: str
    lease_generation: int = 1
    record: OperationRecord | None = None


def _sync_runtime_lease(runtime: OperationRuntime, record: OperationRecord | None) -> None:
    if record is None:
        return
    runtime.record = record
    runtime.lease_generation = int(record.lease_generation or 1)


def begin_operation(
    *,
    tenant_id: str,
    operation_key: str,
    payload: dict[str, Any],
    snapshot: VerifiedSessionSnapshot,
) -> OperationRuntime:
    lease_owner = new_lease_owner()
    with operation_session() as db:
        claim = web_chat_operation_repository.claim(
            db,
            tenant_id=tenant_id,
            operation_key=operation_key,
            payload=payload,
            snapshot=snapshot,
            lease_owner=lease_owner,
        )
        if claim.status == "conflict":
            raise OperationFsmError("operation_conflict", claim.message or "Payload conflict for operation key.")
        if claim.status == "in_progress":
            raise OperationFsmError("operation_in_progress", claim.message or "Operation already in progress.")
        runtime = OperationRuntime(
            tenant_id=tenant_id,
            operation_key=operation_key,
            lease_owner=lease_owner,
            record=claim.record,
        )
        _sync_runtime_lease(runtime, claim.record)
        return runtime


def advance_operation(
    runtime: OperationRuntime,
    target: OperationState,
    *,
    reservation_id: str | None = None,
    result: dict[str, Any] | None = None,
    released: bool | None = None,
) -> OperationRecord:
    with operation_session() as db:
        record = web_chat_operation_repository.transition(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            target=target,
            lease_owner=runtime.lease_owner,
            lease_generation=runtime.lease_generation,
            reservation_id=reservation_id,
            result=result,
            released=released,
        )
    _sync_runtime_lease(runtime, record)
    return record


def try_advance_operation(
    runtime: OperationRuntime,
    from_state: OperationState,
    target: OperationState,
    *,
    reservation_id: str | None = None,
    result: dict[str, Any] | None = None,
    released: bool | None = None,
) -> tuple[OperationRecord | None, bool]:
    with operation_session() as db:
        record, advanced = web_chat_operation_repository.try_transition(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            from_state=from_state,
            target=target,
            lease_owner=runtime.lease_owner,
            lease_generation=runtime.lease_generation,
            reservation_id=reservation_id,
            result=result,
            released=released,
        )
    if record is not None:
        _sync_runtime_lease(runtime, record)
    return record, advanced


def abandon_operation_lease(runtime: OperationRuntime) -> None:
    """Drop lease immediately so a crashed worker cannot block reclaim."""
    with operation_session() as db:
        row = _get_row(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            for_update=True,
        )
        if row is None:
            return
        if row.lease_owner == runtime.lease_owner and lease_generation_of(row) == runtime.lease_generation:
            row.lease_expires_at = _now() - timedelta(seconds=1)
            db.flush()


def refresh_operation_lease(runtime: OperationRuntime) -> OperationRecord | None:
    with operation_session() as db:
        row = _get_row(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
            for_update=True,
        )
        if row is None:
            return None
        assert_lease_fence(row, lease_owner=runtime.lease_owner, lease_generation=runtime.lease_generation)
        extend_lease(row)
        db.flush()
        record = _row_to_record(row)
    _sync_runtime_lease(runtime, record)
    return record


def refresh_operation_runtime(runtime: OperationRuntime) -> OperationRecord | None:
    with operation_session() as db:
        record = web_chat_operation_repository.get(
            db,
            tenant_id=runtime.tenant_id,
            operation_key=runtime.operation_key,
        )
    runtime.record = record
    if record is not None:
        runtime.lease_generation = int(record.lease_generation or 1)
    return record


from services.web_chat.operation_billing import (  # noqa: E402
    ensure_operation_credit_reserved,
    mark_operation_complete_for_ack,
    mark_operation_delivery_acked,
    reconcile_billing_pending,
)

__all__ = [
    "OperationClaimResult",
    "OperationRuntime",
    "abandon_operation_lease",
    "advance_operation",
    "begin_operation",
    "build_followup_payload",
    "build_turn_payload",
    "ensure_operation_credit_reserved",
    "mark_operation_complete_for_ack",
    "mark_operation_delivery_acked",
    "new_lease_owner",
    "operation_session",
    "reconcile_billing_pending",
    "refresh_operation_lease",
    "refresh_operation_runtime",
    "try_advance_operation",
    "web_chat_operation_repository",
]
