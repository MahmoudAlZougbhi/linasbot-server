"""Account deletion grace and export jobs. Nothing is deleted until the grace ends."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

_REQUESTS: dict[str, dict[str, Any]] = {}


def reset_account_requests() -> None:
    _REQUESTS.clear()


def request_deletion(*, tenant_id: str, user_id: str) -> dict[str, Any]:
    row = {
        "id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "status": "pending",
        "grace_until": (datetime.now(UTC) + timedelta(days=14)).isoformat(),
    }
    _REQUESTS[row["id"]] = row
    return row


def cancel_deletion(request_id: str, *, tenant_id: str) -> dict[str, Any]:
    row = _REQUESTS[request_id]
    if row["tenant_id"] != tenant_id:
        raise PermissionError("not_found")
    row["status"] = "cancelled"
    return row


def request_export(*, tenant_id: str) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex,
        "tenant_id": tenant_id,
        "status": "queued",
        "includes": ["settings", "ai_setup", "products", "conversations", "ledger"],
        "expires_in_days": 7,
    }
