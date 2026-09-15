"""When Google/Apple should log into an existing social account instead of 409."""

from __future__ import annotations

from typing import Any

_SOCIAL_CREATED_BY = frozenset({"google-sign-in", "apple-sign-in"})


def is_social_only_account(user: dict[str, Any] | None) -> bool:
    """True for active accounts created via Google/Apple (no password login)."""
    if not user:
        return False
    if str(user.get("status") or "") != "active":
        return False
    if user.get("passwordLoginEnabled") is False:
        return True
    created = str(user.get("createdBy") or "").strip()
    return created in _SOCIAL_CREATED_BY
