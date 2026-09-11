"""Admin force-reindex. Same automatic job as publish; retry only, never a required step."""

from __future__ import annotations

from typing import Any

from services.cm.version_store import read_published_pointer


async def force_reindex_tenant(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ready": False, "reason": "tenant_required", "count": 0, "manual_index_required": False}
    pointer = read_published_pointer(tid)
    if pointer is None:
        return {"ready": False, "reason": "unpublished", "count": 0, "manual_index_required": False}
    revision = str(pointer.content_version_id or "").strip() or "unpublished"
    from services.customer_ai.search.index_schedule import schedule_tenant_index

    result = await schedule_tenant_index(tid, revision=revision, reason="retry")
    return {**result, "manual_index_required": False}
