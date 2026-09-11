"""Admin force-reindex. Uses the same publish-time job and processing budgets."""

from __future__ import annotations

from typing import Any

from services.cm.version_store import read_published_pointer
from services.customer_ai.search.index_job import index_published_tenant


async def force_reindex_tenant(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ready": False, "reason": "tenant_required", "count": 0}
    pointer = read_published_pointer(tid)
    if pointer is None:
        return {"ready": False, "reason": "unpublished", "count": 0}
    revision = str(pointer.content_version_id or "").strip() or "unpublished"
    return await index_published_tenant(tid, revision=revision)
