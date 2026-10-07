"""Newest-first audit rows from catalog edits and platform-owner actions."""

from __future__ import annotations

from typing import Any


def merged_audit_events(*, limit: int = 50) -> list[dict[str, Any]]:
    from services.billing.membership.catalog_admin import audit_log
    from services.team.platform_owner_service import platform_owner_service

    events: list[dict[str, Any]] = []
    for row in audit_log():
        events.append({**row, "source": "catalog", "created_at": float(row.get("created_at") or 0)})
    events.extend(platform_owner_service.list_actions(limit=200))
    events.sort(key=lambda row: float(row.get("created_at") or 0), reverse=True)
    return events[: max(1, min(limit, 200))]
