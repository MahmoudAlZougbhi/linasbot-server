"""Append-only Copilot pricing versions. Newest is active."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from services.billing.membership.copilot_pricing import default_policy, validate_token_policy

_VERSIONS: list[dict[str, Any]] = []


def reset_pricing_for_tests() -> None:
    _VERSIONS.clear()


def active_policy() -> dict[str, Any]:
    if not _VERSIONS:
        return default_policy()
    return dict(_VERSIONS[-1]["body"])


def save_policy(*, body: dict[str, Any], created_by: str, note: str) -> dict[str, Any]:
    if not str(note or "").strip():
        raise ValueError("a change note is required")
    cleaned = validate_token_policy(body)
    row = {
        "version": len(_VERSIONS) + 1,
        "body": cleaned,
        "created_by": created_by or "platform_owner",
        "created_at": datetime.now(UTC).isoformat(),
        "note": note.strip(),
    }
    _VERSIONS.append(row)
    return row


def history() -> list[dict[str, Any]]:
    return list(reversed(_VERSIONS[-50:]))
