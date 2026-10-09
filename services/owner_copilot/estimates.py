"""Pending Copilot estimates. Decline charges nothing. Approve charges actual tokens."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from services.billing.membership.copilot_pricing import messages_for_tokens

_ROWS: dict[str, dict[str, Any]] = {}


class EstimateError(Exception):
    def __init__(self, code: str, status: int) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


def reset_estimates_for_tests() -> None:
    _ROWS.clear()


def create_estimate(**fields: Any) -> dict[str, Any]:
    estimate_id = uuid.uuid4().hex
    row = {
        "id": estimate_id,
        "status": "pending",
        "charged": None,
        "expires_at": (datetime.now(UTC) + timedelta(minutes=10)).isoformat(),
        **fields,
    }
    _ROWS[estimate_id] = row
    return row


def get_estimate(estimate_id: str) -> dict[str, Any]:
    row = _ROWS.get(estimate_id)
    if row is None:
        raise EstimateError("not_found", 404)
    return row


def decline(estimate_id: str) -> dict[str, Any]:
    row = get_estimate(estimate_id)
    row["status"] = "declined"
    row["charged"] = 0
    row["ledger_reason"] = "copilot_declined"
    return row


def approve(estimate_id: str, *, actual_tokens: int, tenant_id: str, user_id: str) -> dict[str, Any]:
    row = get_estimate(estimate_id)
    if row.get("tenant_id") != tenant_id or row.get("user_id") != user_id:
        raise EstimateError("forbidden", 403)
    if row["status"] == "approved":
        return row
    if row["status"] != "pending":
        raise EstimateError("not_pending", 409)
    expires = datetime.fromisoformat(str(row["expires_at"]))
    if datetime.now(UTC) > expires:
        raise EstimateError("expired", 410)
    policy = row.get("policy") if isinstance(row.get("policy"), dict) else None
    charged = messages_for_tokens(actual_tokens, policy)
    row["status"] = "approved"
    row["charged"] = charged
    row["actual_tokens"] = int(actual_tokens)
    return row
