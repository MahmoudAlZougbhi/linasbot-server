"""Customer Requests package — structured work items (Postgres SoT)."""

from __future__ import annotations

from services.requests.constants import (
    CM_SECTION_REQUESTS_APPOINTMENTS,
    PERSISTABLE_REQUEST_TYPES,
    REQUEST_PERMISSION_KEYS,
    REQUEST_TYPES,
    STATUSES,
)
from services.requests.state_machine import (
    InvalidRequestTransition,
    can_transition,
    require_transition,
    resolve_final_action_status,
)

__all__ = [
    "CM_SECTION_REQUESTS_APPOINTMENTS",
    "InvalidRequestTransition",
    "PERSISTABLE_REQUEST_TYPES",
    "REQUEST_PERMISSION_KEYS",
    "REQUEST_TYPES",
    "STATUSES",
    "can_transition",
    "require_transition",
    "resolve_final_action_status",
]
