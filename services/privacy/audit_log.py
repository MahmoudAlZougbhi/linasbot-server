"""Append-only audit rows for owner and platform actions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

_ROWS: list[dict[str, Any]] = []


def reset_audit_log() -> None:
    _ROWS.clear()


def write_audit(
    *,
    tenant_id: str | None,
    actor_user_id: str,
    actor_role: str,
    action: str,
    target: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "actor_user_id": actor_user_id,
        "actor_role": actor_role,
        "action": action,
        "target": target,
        "before": before or {},
        "after": after or {},
        "created_at": datetime.now(UTC).isoformat(),
    }
    _ROWS.append(row)
    return row


def read_audit(*, tenant_id: str | None, platform: bool) -> list[dict[str, Any]]:
    if platform:
        return list(_ROWS)
    return [row for row in _ROWS if row["tenant_id"] == tenant_id]
