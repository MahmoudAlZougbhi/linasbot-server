"""Index health status for Customer Brain retrieval freshness."""

from __future__ import annotations

from typing import Any, Literal

IndexHealth = Literal[
    "NO_INDEX",
    "BUILDING",
    "READY",
    "ACTIVE",
    "STALE",
    "FAILED",
    "UNPUBLISHED",
    "MISSING",
    "INDEXING",
]

_STATUS: dict[str, dict[str, Any]] = {}


def _normalize(status: str) -> str:
    if status == "INDEXING":
        return "BUILDING"
    if status == "MISSING":
        return "NO_INDEX"
    return status


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
        "status": _normalize(status),
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
        return {"tenant_id": "", "status": "NO_INDEX", "reason": "missing_tenant"}
    try:
        from services.customer_ai.search.index_lifecycle import owner_status

        durable = owner_status(tid)
        if str(durable.get("status") or "NO_INDEX") != "NO_INDEX" or str(durable.get("failure_reason") or ""):
            return {
                "tenant_id": tid,
                "status": durable.get("status") or "NO_INDEX",
                "content_version": durable.get("content_revision") or "",
                "index_version": durable.get("active_version") or "",
                "reason": durable.get("failure_reason") or "",
                "manual_index_required": False,
            }
    except Exception:
        pass
    return dict(_STATUS.get(tid) or {"tenant_id": tid, "status": "NO_INDEX", "reason": "unknown"})


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
        return "BUILDING"
    if not content_version:
        return "UNPUBLISHED"
    if not index_version or content_version != index_version:
        return "STALE"
    return "ACTIVE"


def reset_index_status_for_tests() -> None:
    _STATUS.clear()
