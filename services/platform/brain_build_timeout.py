"""Stop a brain index from staying BUILDING forever."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_TIMEOUT_REASON = "publish_timeout"


def _updated_at(row: dict[str, Any]) -> datetime | None:
    raw = row.get("updated_at")
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def expire_building(row: dict[str, Any], *, now: datetime, timeout_seconds: int) -> dict[str, Any] | None:
    """Return a FAILED row when BUILDING is older than the timeout. Otherwise None."""
    if str(row.get("status") or "") != "BUILDING":
        return None
    updated = _updated_at(row)
    if updated is None:
        return None
    age = (now - updated).total_seconds()
    if age <= timeout_seconds:
        return None
    retry_count = int(row.get("retry_count") or 0) + 1
    return {
        **row,
        "status": "FAILED",
        "failure_reason": _TIMEOUT_REASON,
        "retry_count": retry_count,
        "updated_at": now.isoformat(),
    }
