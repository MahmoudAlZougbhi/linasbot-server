"""Assignable role policy for tenant RBAC.

``platform_owner`` is fail-closed: never via public register or tenant user APIs.
Only offline CLI with an explicit created_by marker may assign it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Final

TENANT_ASSIGNABLE_ROLES: Final[frozenset[str]] = frozenset({"admin", "operator", "viewer"})
PLATFORM_OWNER_ROLE: Final[str] = "platform_owner"
PLATFORM_OWNER_CREATED_BY: Final[frozenset[str]] = frozenset(
    {
        "cli-provision-platform-owner",
    }
)
_CUSTOM_ROLE_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z][a-z0-9_-]{1,39}$")


class RoleAssignmentError(ValueError):
    """Raised when a role cannot be assigned under current policy."""


def is_platform_owner_role(role: str | None) -> bool:
    return (role or "").strip().lower() == PLATFORM_OWNER_ROLE


def assert_assignable_role(
    role: str,
    *,
    created_by: str | None = None,
    custom_role_ids: Iterable[str] | None = None,
) -> str:
    """Return normalized role or raise RoleAssignmentError."""
    normalized = (role or "").strip().lower()
    if not normalized:
        raise RoleAssignmentError("Role is required")
    if normalized in TENANT_ASSIGNABLE_ROLES:
        return normalized
    if normalized == PLATFORM_OWNER_ROLE:
        if (created_by or "").strip() in PLATFORM_OWNER_CREATED_BY:
            return PLATFORM_OWNER_ROLE
        raise RoleAssignmentError(
            "platform_owner can only be assigned via offline CLI "
            "(--role platform_owner); never via public register or tenant APIs"
        )
    allowed = {str(item).strip().lower() for item in (custom_role_ids or [])}
    if normalized in allowed and _CUSTOM_ROLE_RE.fullmatch(normalized):
        return normalized
    raise RoleAssignmentError(f"Unknown or unassignable role: {normalized}")
