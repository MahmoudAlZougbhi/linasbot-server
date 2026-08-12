"""Server-side status transitions for Customer Requests."""

from __future__ import annotations

from services.requests.constants import REQUEST_TYPES, STATUSES

# type -> frozenset of (from_status, to_status)
_TRANSITIONS: dict[str, frozenset[tuple[str, str]]] = {
    "APPOINTMENT": frozenset(
        {
            ("NEW", "IN_REVIEW"),
            ("IN_REVIEW", "WAITING_FOR_CUSTOMER"),
            ("WAITING_FOR_CUSTOMER", "IN_REVIEW"),
            ("IN_REVIEW", "CONFIRMED"),
            ("WAITING_FOR_CUSTOMER", "CONFIRMED"),
            ("CONFIRMED", "COMPLETED"),
            ("NEW", "CANCELLED"),
            ("IN_REVIEW", "CANCELLED"),
            ("WAITING_FOR_CUSTOMER", "CANCELLED"),
            ("CONFIRMED", "CANCELLED"),
        }
    ),
    "ORDER": frozenset(
        {
            ("NEW", "IN_REVIEW"),
            ("IN_REVIEW", "WAITING_FOR_CUSTOMER"),
            ("WAITING_FOR_CUSTOMER", "IN_REVIEW"),
            ("IN_REVIEW", "CONFIRMED"),
            ("WAITING_FOR_CUSTOMER", "CONFIRMED"),
            ("CONFIRMED", "READY"),
            ("READY", "COMPLETED"),
            ("NEW", "CANCELLED"),
            ("IN_REVIEW", "CANCELLED"),
            ("WAITING_FOR_CUSTOMER", "CANCELLED"),
            ("CONFIRMED", "CANCELLED"),
            ("READY", "CANCELLED"),
        }
    ),
    "OTHER": frozenset(
        {
            ("NEW", "IN_REVIEW"),
            ("IN_REVIEW", "WAITING_FOR_CUSTOMER"),
            ("WAITING_FOR_CUSTOMER", "IN_REVIEW"),
            ("IN_REVIEW", "COMPLETED"),
            ("WAITING_FOR_CUSTOMER", "COMPLETED"),
            ("NEW", "CANCELLED"),
            ("IN_REVIEW", "CANCELLED"),
            ("WAITING_FOR_CUSTOMER", "CANCELLED"),
        }
    ),
}

# Final owner actions → target status
FINAL_ACTIONS: dict[str, dict[str, str]] = {
    "APPOINTMENT": {"confirm_appointment": "CONFIRMED"},
    "ORDER": {"mark_ready": "READY"},
    "OTHER": {"complete_request": "COMPLETED"},
}


class InvalidRequestTransition(ValueError):
    """Raised when a status change is not allowed for the request type."""


def assert_known_type(request_type: str) -> str:
    rt = (request_type or "").strip().upper()
    if rt not in REQUEST_TYPES:
        raise InvalidRequestTransition(f"unknown request_type={request_type!r}")
    return rt


def assert_known_status(status: str) -> str:
    st = (status or "").strip().upper()
    if st not in STATUSES:
        raise InvalidRequestTransition(f"unknown status={status!r}")
    return st


def can_transition(request_type: str, from_status: str, to_status: str) -> bool:
    rt = assert_known_type(request_type)
    frm = assert_known_status(from_status)
    to = assert_known_status(to_status)
    if frm == to:
        return False
    return (frm, to) in _TRANSITIONS[rt]


def require_transition(request_type: str, from_status: str, to_status: str) -> None:
    if not can_transition(request_type, from_status, to_status):
        raise InvalidRequestTransition(f"invalid transition {from_status!r} → {to_status!r} for {request_type!r}")


def resolve_final_action_status(request_type: str, action: str) -> str:
    rt = assert_known_type(request_type)
    key = (action or "").strip().lower()
    mapping = FINAL_ACTIONS.get(rt) or {}
    if key not in mapping:
        raise InvalidRequestTransition(f"unknown final action {action!r} for {rt}")
    return mapping[key]
