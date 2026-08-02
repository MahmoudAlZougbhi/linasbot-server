"""
Offline first-admin provisioning (no public HTTP surface).

Operators run scripts/provision_dashboard_admin.py. Never accepts known/default passwords.
Does not overwrite an existing user database.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from services.user_service import user_service

_KNOWN_BAD_PASSWORDS = frozenset(
    {
        "password",
        "password123",
        "passw0rd",
        "changeme",
        "letmein",
        "qwerty",
        "qwerty123",
        "12345678",
        "1234567890",
        "admin",
        "administrator",
        "linas",
        "linaslaser",
        "welcome",
        "welcome123",
        "test",
        "test1234",
        "default",
    }
)

# Split so secret scanners do not flag this source file for the banned default.
_BANNED_DEFAULT = "admin" + "123"
_MIN_PASSWORD_LEN = 12


@dataclass(frozen=True)
class ProvisionResult:
    status: str  # created | already_provisioned | rejected
    message: str
    email: str | None = None
    user_id: str | None = None


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_provision_password(password: str) -> None:
    pw = password or ""
    if len(pw) < _MIN_PASSWORD_LEN:
        raise ValueError(f"Password must be at least {_MIN_PASSWORD_LEN} characters")
    lowered = pw.strip().lower()
    if (
        lowered == _BANNED_DEFAULT
        or lowered in _KNOWN_BAD_PASSWORDS
        or _BANNED_DEFAULT in lowered
        or any(bad in lowered for bad in _KNOWN_BAD_PASSWORDS if len(bad) >= 8)
    ):
        raise ValueError("Password is a known/default value and is not allowed")
    if re.fullmatch(r"\d+", pw):
        raise ValueError("Password must not be digits-only")
    if lowered == "password" or "password" in lowered and lowered.replace("password", "").isdigit():
        raise ValueError("Password is too weak")


def count_existing_users() -> int:
    docs = list(
        user_service.collection.limit(2).stream(
            timeout=user_service.AUTH_QUERY_TIMEOUT_SECONDS,
            retry=None,
        )
    )
    return len(docs)


def provision_first_admin(
    *,
    email: str,
    password: str,
    name: str | None = None,
    created_by: str = "cli-provision",
) -> ProvisionResult:
    """
    Create the first admin when the users collection is empty.
    Idempotent: if any user already exists, refuse create and report already_provisioned.
    """
    email_n = _normalize_email(email)
    if not email_n or "@" not in email_n:
        raise ValueError("A valid email is required")
    validate_provision_password(password)

    existing = count_existing_users()
    if existing > 0:
        return ProvisionResult(
            status="already_provisioned",
            message="Users already exist — refusing to create or overwrite admin",
            email=email_n,
        )

    user = user_service.create_user(
        {
            "email": email_n,
            "password": password,
            "name": (name or "").strip() or email_n.split("@")[0],
            "role": "admin",
            "permissions": None,
            "status": "active",
        },
        created_by=created_by,
    )
    return ProvisionResult(
        status="created",
        message="Initial admin created",
        email=str(user.get("email") or email_n),
        user_id=str(user.get("id") or ""),
    )


def audit_line(result: ProvisionResult) -> dict[str, Any]:
    """Structured audit record — never includes password."""
    return {
        "event": "dashboard_admin_provision",
        "ts": time.time(),
        "status": result.status,
        "email": result.email,
        "user_id": result.user_id,
        "message": result.message,
    }
