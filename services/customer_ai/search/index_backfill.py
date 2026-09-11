"""Bounded backfill for published tenants missing an active contextual index."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.cm.version_store import read_published_pointer
from storage.persistent_storage import get_data_root

DEFAULT_BACKFILL_LIMIT = 3


def published_tenant_ids() -> list[str]:
    root = Path(get_data_root()) / "tenants"
    if not root.is_dir():
        return []
    out: list[str] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        if (path / "cm" / "published" / "pointer.json").is_file():
            out.append(path.name)
    return out


def tenant_needs_index(tenant_id: str) -> bool:
    from services.customer_ai.search.index_lifecycle import get_lifecycle

    pointer = read_published_pointer(tenant_id)
    if pointer is None:
        return False
    rev = str(pointer.content_version_id or "").strip()
    if not rev:
        return False
    row = get_lifecycle(tenant_id)
    status = str(row.get("status") or "NO_INDEX")
    if status == "BUILDING":
        return False
    if status == "ACTIVE" and str(row.get("content_revision") or "") == rev:
        return False
    return True


async def enqueue_stale_or_missing(
    *,
    limit: int = DEFAULT_BACKFILL_LIMIT,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    from services.customer_ai.search.index_schedule import schedule_tenant_index

    skip_ids = {item.strip() for item in (skip or set()) if str(item).strip()}
    scheduled: list[dict[str, Any]] = []
    skipped = 0
    for tid in published_tenant_ids():
        if tid in skip_ids:
            skipped += 1
            continue
        if not tenant_needs_index(tid):
            continue
        result = await schedule_tenant_index(tid, reason="backfill")
        scheduled.append(
            {
                "tenant_id": tid,
                "queued": bool(result.get("queued")),
                "health": result.get("health"),
                "reason": result.get("reason"),
            }
        )
        if len(scheduled) >= max(1, int(limit)):
            break
    return {
        "limit": max(1, int(limit)),
        "scheduled_count": len(scheduled),
        "skipped_current": skipped,
        "scheduled": scheduled,
        "manual_index_required": False,
    }
