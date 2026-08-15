"""Monotonic lease fencing for durable web-chat operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.web_chat.operation_fsm import OperationFsmError
from services.web_chat.pg_models import WebChatOperationRow

LEASE_TTL_SECONDS = 120


def lease_generation_of(row: WebChatOperationRow) -> int:
    return int(getattr(row, "lease_generation", 1) or 1)


def assert_lease_fence(
    row: WebChatOperationRow,
    *,
    lease_owner: str,
    lease_generation: int,
) -> None:
    if row.lease_owner != lease_owner or lease_generation_of(row) != int(lease_generation):
        raise OperationFsmError(
            "lease_fence_stale",
            "Stale lease owner or generation for operation transition.",
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def lease_active(row: WebChatOperationRow, *, now: datetime | None = None) -> bool:
    current = _as_utc(now or datetime.now(UTC))
    expires_at = row.lease_expires_at
    if not row.lease_owner or expires_at is None:
        return False
    return _as_utc(expires_at) > current


def handoff_lease(row: WebChatOperationRow, *, lease_owner: str) -> int:
    """Expire stale ownership and issue a new monotonic generation."""
    generation = lease_generation_of(row) + 1
    row.lease_generation = generation
    row.lease_owner = lease_owner
    row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_TTL_SECONDS)
    return generation


def extend_lease(row: WebChatOperationRow) -> None:
    row.lease_expires_at = datetime.now(UTC) + timedelta(seconds=LEASE_TTL_SECONDS)
