"""Row mapping helpers for Website Chat operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.integrations.web_chat.operation_fsm import OperationRecord, OperationState, VerifiedSessionSnapshot
from services.integrations.web_chat.operation_lease import LEASE_TTL_SECONDS, lease_generation_of
from services.integrations.web_chat.pg_models import WebChatOperationRow


def utc_now() -> datetime:
    return datetime.now(UTC)


def lease_ttl_seconds() -> int:
    return LEASE_TTL_SECONDS


def row_to_record(row: WebChatOperationRow) -> OperationRecord:
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


def get_operation_row(
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
