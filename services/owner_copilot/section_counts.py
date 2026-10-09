"""Counts come from the records, not from the model."""

from __future__ import annotations

from typing import Any


def count_records(items: list[Any]) -> dict[str, int]:
    total = 0
    active = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        total += 1
        status = str(item.get("status") or "active").strip().lower()
        if status in {"active", "published", "live"}:
            active += 1
    return {"active": active, "total": total}
