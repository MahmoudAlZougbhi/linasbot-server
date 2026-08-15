"""Durable Website Chat operation/credit finite-state machine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class OperationState(StrEnum):
    CLAIMED = "claimed"
    RESERVED = "reserved"
    REPLY_READY = "reply_ready"
    DURABLE_VISIBLE = "durable_visible"
    CAPTURED = "captured"
    COMPLETE = "complete"
    RELEASED = "released"
    RELEASE_PENDING = "release_pending"
    BILLING_PENDING = "billing_pending"


TERMINAL_STATES = frozenset(
    {
        OperationState.COMPLETE,
        OperationState.RELEASED,
    }
)
VISIBLE_STATES = frozenset(
    {
        OperationState.DURABLE_VISIBLE,
        OperationState.CAPTURED,
        OperationState.COMPLETE,
        OperationState.BILLING_PENDING,
    }
)
REPLAYABLE_STATES = frozenset(
    {
        OperationState.REPLY_READY,
        OperationState.DURABLE_VISIBLE,
        OperationState.CAPTURED,
        OperationState.COMPLETE,
        OperationState.BILLING_PENDING,
    }
)


class OperationFsmError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class VerifiedSessionSnapshot:
    """Immutable tenant/widget/session binding verified at claim time."""

    tenant_id: str
    widget_key: str
    session_id: str
    authority_hash: str

    def to_dict(self) -> dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "widget_key": self.widget_key,
            "session_id": self.session_id,
            "authority_hash": self.authority_hash,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> VerifiedSessionSnapshot:
        raw = dict(data or {})
        return cls(
            tenant_id=str(raw.get("tenant_id") or "").strip().lower(),
            widget_key=str(raw.get("widget_key") or "").strip(),
            session_id=str(raw.get("session_id") or "").strip(),
            authority_hash=str(raw.get("authority_hash") or "").strip(),
        )


def canonical_payload_hash(payload: Mapping[str, Any]) -> str:
    """Stable SHA-256 over canonical JSON for idempotent replay detection."""
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def stable_operation_key(*, session_id: str, client_key: str) -> str:
    sid = str(session_id or "").strip()
    key = str(client_key or "").strip()
    if not sid or not key:
        raise OperationFsmError("invalid_operation_key", "session_id and client_key are required.")
    return f"{sid}:{key}"


def web_chat_credit_request_id(*, session_id: str, operation_key: str, attempt: int) -> str:
    """Attempt-scoped ledger request id; preserves client idempotency via operation_key."""
    sid = str(session_id or "").strip()
    op = str(operation_key or "").strip()
    if not sid or not op:
        raise OperationFsmError("invalid_operation_key", "session_id and operation_key are required.")
    generation = max(1, int(attempt or 1))
    return f"web:{sid}:{op}:a{generation}"


def is_visible_state(state: OperationState | str) -> bool:
    return OperationState(str(state)) in VISIBLE_STATES


def is_terminal_state(state: OperationState | str) -> bool:
    return OperationState(str(state)) in TERMINAL_STATES


def may_release_credit(state: OperationState | str) -> bool:
    """Pre-visible failures release once; visible results never release."""
    op = OperationState(str(state))
    return op not in VISIBLE_STATES and op not in {OperationState.RELEASED, OperationState.RELEASE_PENDING}


def assert_transition(current: OperationState | str, target: OperationState) -> None:
    cur = OperationState(str(current))
    allowed: dict[OperationState, frozenset[OperationState]] = {
        OperationState.CLAIMED: frozenset(
            {OperationState.RESERVED, OperationState.RELEASED, OperationState.REPLY_READY}
        ),
        OperationState.RESERVED: frozenset(
            {
                OperationState.REPLY_READY,
                OperationState.RELEASED,
                OperationState.RELEASE_PENDING,
                OperationState.BILLING_PENDING,
            }
        ),
        OperationState.REPLY_READY: frozenset(
            {
                OperationState.DURABLE_VISIBLE,
                OperationState.RELEASED,
                OperationState.RELEASE_PENDING,
                OperationState.BILLING_PENDING,
            }
        ),
        OperationState.DURABLE_VISIBLE: frozenset(
            {
                OperationState.CAPTURED,
                OperationState.BILLING_PENDING,
                OperationState.COMPLETE,
                OperationState.REPLY_READY,
            }
        ),
        OperationState.CAPTURED: frozenset({OperationState.COMPLETE, OperationState.BILLING_PENDING}),
        OperationState.BILLING_PENDING: frozenset({OperationState.CAPTURED, OperationState.COMPLETE}),
        OperationState.COMPLETE: frozenset(),
        OperationState.RELEASED: frozenset(),
        OperationState.RELEASE_PENDING: frozenset({OperationState.RELEASED}),
    }
    if target not in allowed.get(cur, frozenset()):
        raise OperationFsmError(
            "invalid_transition",
            f"Cannot transition operation from {cur.value} to {target.value}.",
        )


@dataclass(frozen=True)
class OperationRecord:
    tenant_id: str
    operation_key: str
    payload_hash: str
    state: OperationState
    attempt: int
    lease_owner: str
    reservation_id: str | None
    result: dict[str, Any] | None
    snapshot: VerifiedSessionSnapshot
    lease_generation: int = 1
    released: bool = False

    def canonical_reply(self) -> str | None:
        if not self.result:
            return None
        reply = self.result.get("reply_text")
        return str(reply).strip() if reply is not None else None
