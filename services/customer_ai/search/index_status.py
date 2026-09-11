"""Index health status for Customer Brain retrieval freshness."""

from __future__ import annotations

from typing import Any, Literal

IndexHealth = Literal["READY", "INDEXING", "STALE", "FAILED", "UNPUBLISHED", "MISSING"]

_STATUS: dict[str, dict[str, Any]] = {}


def set_index_status(
    tenant_id: str,
    *,
    status: IndexHealth,
    content_version: str = "",
    index_version: str = "",
    reason: str = "",
) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    row = {
        "tenant_id": tid,
        "status": status,
        "content_version": content_version,
        "index_version": index_version,
        "reason": reason,
    }
    if tid:
        _STATUS[tid] = row
    return row


def get_index_status(tenant_id: str) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"tenant_id": "", "status": "MISSING", "reason": "missing_tenant"}
    return dict(_STATUS.get(tid) or {"tenant_id": tid, "status": "MISSING", "reason": "unknown"})


def mark_stale(tenant_id: str, *, content_version: str = "", reason: str = "content_changed") -> dict[str, Any]:
    prev = get_index_status(tenant_id)
    return set_index_status(
        tenant_id,
        status="STALE",
        content_version=content_version or str(prev.get("content_version") or ""),
        index_version=str(prev.get("index_version") or ""),
        reason=reason,
    )


def resolve_health(
    *, content_version: str, index_version: str, indexing: bool = False, failed: bool = False
) -> IndexHealth:
    if failed:
        return "FAILED"
    if indexing:
        return "INDEXING"
    if not content_version:
        return "UNPUBLISHED"
    if not index_version or content_version != index_version:
        return "STALE"
    return "READY"


def reset_index_status_for_tests() -> None:
    _STATUS.clear()
