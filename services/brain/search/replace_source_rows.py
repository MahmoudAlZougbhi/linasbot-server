"""Drop leftover chunk rows for a source_id when rewriting an index version."""

from __future__ import annotations

from typing import Any


def drop_stale_source_rows(session: Any | None, rows: list[dict[str, Any]]) -> None:
    """Remove prior chunk_ids for the same tenant/space/source/version as ``rows``.

    Stops leftover mechanical splitter ids from sitting next to Luna ids.
    """
    groups: dict[tuple[str, str, str, str], set[str]] = {}
    for row in rows:
        tenant_id = str(row.get("tenant_id") or "").strip()
        space_id = str(row.get("space_id") or "").strip()
        source_id = str(row.get("source_id") or "").strip()
        version = str(row.get("index_version") or "").strip()
        if not tenant_id or not source_id:
            continue
        key = (tenant_id, space_id, source_id, version)
        groups.setdefault(key, set()).add(str(row.get("chunk_id") or ""))
    if not groups:
        return
    if session is None:
        _drop_memory(groups)
        return
    _drop_sql(session, groups)


def _drop_memory(groups: dict[tuple[str, str, str, str], set[str]]) -> None:
    from services.brain.search.store import _MEMORY

    for (tenant_id, space_id, source_id, version), keep in groups.items():
        bucket = _MEMORY.get(tenant_id)
        if not bucket:
            continue
        bucket[:] = [
            item
            for item in bucket
            if not (
                str(item.get("space_id") or "") == space_id
                and str(item.get("source_id") or "") == source_id
                and str(item.get("index_version") or "") == version
                and str(item.get("chunk_id") or "") not in keep
            )
        ]


def _drop_sql(session: Any, groups: dict[tuple[str, str, str, str], set[str]]) -> None:
    from sqlalchemy import text

    try:
        for (tenant_id, space_id, source_id, version), keep in groups.items():
            session.execute(
                text(
                    """
                    DELETE FROM customer_ai_search_documents
                    WHERE tenant_id = :tenant_id
                      AND space_id = :space_id
                      AND source_id = :source_id
                      AND index_version = :index_version
                      AND NOT (chunk_id = ANY(:keep))
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "space_id": space_id,
                    "source_id": source_id,
                    "index_version": version,
                    "keep": sorted(keep),
                },
            )
    except Exception:
        return
