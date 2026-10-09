"""Decide whether a section save only removes items."""

from __future__ import annotations

from typing import Any

from services.billing.membership.daily_edits import payload_hash

_LIST_KEYS = ("items", "rules", "catalog", "entries")


def classify_section_change(section: str, current: object, payload: object) -> str:
    """Return noop, delete_only, or billable."""
    _ = section
    if payload_hash(current) == payload_hash(payload):
        return "noop"
    before = _indexed(current)
    after = _indexed(payload)
    if before is None or after is None:
        return "billable"
    if not set(after).issubset(before):
        return "billable"
    for key, item in after.items():
        if payload_hash(item) != payload_hash(before[key]):
            return "billable"
    if len(after) < len(before):
        return "delete_only"
    return "billable"


def _indexed(payload: object) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    rows: list[Any] | None = None
    for key in _LIST_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            rows = value
            break
    if rows is None:
        return None
    indexed: dict[str, Any] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or item.get("qa_group_id") or "").strip()
        if item_id:
            indexed[item_id] = item
    return indexed
