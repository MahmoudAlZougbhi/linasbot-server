"""Cap published request rules at 10 per type (ORDER / APPOINTMENT / HUMAN / OTHER)."""

from __future__ import annotations

from typing import Any

from services.requests.constants import MAX_RULES_PER_REQUEST_TYPE, REQUEST_TYPES

REQUEST_RULE_LIMIT_CODE = "REQUEST_RULE_LIMIT"


class RequestRuleLimitError(ValueError):
    """Owner tried to save more than the per-type request-rule cap."""

    code = REQUEST_RULE_LIMIT_CODE

    def __init__(self, message: str, *, request_type: str = "", count: int = 0) -> None:
        super().__init__(message)
        self.request_type = request_type
        self.count = count
        self.limit = MAX_RULES_PER_REQUEST_TYPE


def _rule_type(row: object) -> str:
    if isinstance(row, dict):
        raw = row.get("type")
    else:
        raw = getattr(row, "type", "")
    return str(raw or "").strip().upper()


def count_rules_by_type(rules: object) -> dict[str, int]:
    counts = {code: 0 for code in REQUEST_TYPES}
    if not isinstance(rules, list):
        return counts
    for row in rules:
        code = _rule_type(row)
        if code in counts:
            counts[code] += 1
    return counts


def request_rule_limit_error(counts: dict[str, int]) -> RequestRuleLimitError | None:
    for code, total in counts.items():
        if code not in REQUEST_TYPES:
            continue
        if total > MAX_RULES_PER_REQUEST_TYPE:
            return RequestRuleLimitError(
                f"Maximum {MAX_RULES_PER_REQUEST_TYPE} {code} request rules per tenant. This save has {total}.",
                request_type=code,
                count=total,
            )
    return None


def assert_request_rule_limits(payload: dict[str, Any] | None) -> None:
    raw = payload if isinstance(payload, dict) else {}
    err = request_rule_limit_error(count_rules_by_type(raw.get("rules")))
    if err is not None:
        raise err


def request_rule_limit_failures(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    raw = payload if isinstance(payload, dict) else {}
    err = request_rule_limit_error(count_rules_by_type(raw.get("rules")))
    if err is None:
        return []
    return [
        {
            "level": "error",
            "severity": "error",
            "code": REQUEST_RULE_LIMIT_CODE,
            "message": str(err),
            "section": "requests_appointments",
            "path": "requests_appointments.payload.rules",
            "details": {"request_type": err.request_type, "count": str(err.count)},
        }
    ]
