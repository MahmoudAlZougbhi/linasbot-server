"""Tenant-scoped search documents. Missing session/pgvector is index_not_ready."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.customer_ai.search.readiness import probe_pgvector

_MEMORY: dict[str, list[dict[str, Any]]] = {}
_POINTERS: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class StoreHit:
    doc_id: str
    tenant_id: str
    source_family: str
    source_id: str
    title: str
    search_text: str
    score: float


@dataclass(frozen=True)
class StoreQueryResult:
    outcome: str
    items: list[StoreHit] = field(default_factory=list)
    reason: str = ""


def _pointer_key(tenant_id: str, space_id: str, family: str) -> str:
    return f"{tenant_id}|{space_id}|{family}"


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    n1 = sum(a * a for a in left) ** 0.5
    n2 = sum(b * b for b in right) ** 0.5
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{float(v):.8f}" for v in values) + "]"


def reset_memory_store() -> None:
    _MEMORY.clear()
    _POINTERS.clear()


def write_documents(
    session: Any | None,
    rows: list[dict[str, Any]],
    vectors: list[list[float]],
) -> dict[str, Any]:
    if len(rows) != len(vectors):
        return {"ok": False, "reason": "provider_error", "count": 0}
    if session is None:
        return _write_memory(rows, vectors)
    if not probe_pgvector(session):
        return {"ok": False, "reason": "index_not_ready", "count": 0}
    return _write_sql(session, rows, vectors)


def query_similar(
    session: Any | None,
    *,
    tenant_id: str,
    space_id: str,
    vector: list[float],
    families: set[str] | None = None,
    limit: int = 20,
    index_version: str | None = None,
) -> StoreQueryResult:
    tid = (tenant_id or "").strip()
    if not tid:
        return StoreQueryResult(outcome="permission_denied", reason="missing_tenant")
    active = (index_version or "").strip() or _active_version_for(tid, space_id)
    if session is None:
        return _query_memory(tid, space_id, vector, families, limit, active_version=active)
    if not probe_pgvector(session):
        return StoreQueryResult(outcome="index_not_ready", reason="index_not_ready")
    return _query_sql(session, tid, space_id, vector, families, limit, active_version=active)


def _active_version_for(tenant_id: str, space_id: str) -> str:
    for row in _POINTERS.values():
        if (
            isinstance(row, dict)
            and row.get("tenant_id") == tenant_id
            and row.get("space_id") == space_id
            and row.get("ready")
        ):
            return str(row.get("active_version") or "")
    return ""


def activate_pointer(
    session: Any | None,
    *,
    tenant_id: str,
    space_id: str,
    source_family: str,
    version: str,
    count: int,
    source_revision: str = "",
) -> dict[str, Any]:
    key = _pointer_key(tenant_id, space_id, source_family)
    previous = _POINTERS.get(key) or {}
    record = {
        "tenant_id": tenant_id,
        "space_id": space_id,
        "source_family": source_family,
        "active_version": version,
        "rollback_version": str(previous.get("active_version") or ""),
        "ready": True,
        "reason": "ok",
        "source_revision": source_revision,
        "record_count": count,
    }
    _POINTERS[key] = record
    if session is None:
        return {"ok": True, "pointer": record, "backend": "memory"}
    if not probe_pgvector(session):
        return {"ok": False, "reason": "index_not_ready"}
    try:
        import hashlib

        from sqlalchemy import text

        space_digest = hashlib.sha1(space_id.encode("utf-8")).hexdigest()[:10]
        pointer_id = f"{tenant_id}:{source_family}:{space_digest}"[:64]
        session.execute(
            text(
                """
                INSERT INTO customer_ai_index_pointers
                    (id, tenant_id, space_id, source_family, active_version, rollback_version,
                     ready, reason, source_revision, record_count)
                VALUES
                    (:id, :tenant_id, :space_id, :source_family, :active_version, :rollback_version,
                     true, 'ok', :source_revision, :record_count)
                ON CONFLICT (tenant_id, space_id, source_family) DO UPDATE SET
                    rollback_version = customer_ai_index_pointers.active_version,
                    active_version = EXCLUDED.active_version,
                    ready = true,
                    reason = 'ok',
                    source_revision = EXCLUDED.source_revision,
                    record_count = EXCLUDED.record_count,
                    updated_at = now()
                """
            ),
            {
                "id": pointer_id,
                "tenant_id": tenant_id,
                "space_id": space_id,
                "source_family": source_family,
                "active_version": version,
                "rollback_version": str(previous.get("active_version") or ""),
                "source_revision": source_revision,
                "record_count": count,
            },
        )
        return {"ok": True, "pointer": record, "backend": "pgvector"}
    except Exception:
        return {"ok": False, "reason": "index_not_ready"}


def rollback_pointer(
    session: Any | None,
    *,
    tenant_id: str,
    space_id: str,
    source_family: str,
) -> dict[str, Any]:
    key = _pointer_key(tenant_id, space_id, source_family)
    current = _POINTERS.get(key)
    if session is not None and (not current or not current.get("rollback_version")):
        try:
            from sqlalchemy import text

            row = (
                session.execute(
                    text(
                        """
                    SELECT tenant_id, space_id, source_family, active_version, rollback_version,
                           ready, reason, source_revision, record_count
                    FROM customer_ai_index_pointers
                    WHERE tenant_id = :tenant_id AND space_id = :space_id AND source_family = :source_family
                    """
                    ),
                    {"tenant_id": tenant_id, "space_id": space_id, "source_family": source_family},
                )
                .mappings()
                .first()
            )
            if row:
                current = dict(row)
                _POINTERS[key] = current
        except Exception:
            current = current
    if not current or not current.get("rollback_version"):
        return {"ok": False, "reason": "no_rollback"}
    rolled = {
        **current,
        "active_version": current["rollback_version"],
        "rollback_version": current["active_version"],
        "ready": True,
        "reason": "rollback",
    }
    _POINTERS[key] = rolled
    if session is None:
        return {"ok": True, "pointer": rolled, "backend": "memory"}
    try:
        from sqlalchemy import text

        session.execute(
            text(
                """
                UPDATE customer_ai_index_pointers
                SET active_version = :active_version,
                    rollback_version = :rollback_version,
                    ready = true,
                    reason = 'rollback',
                    updated_at = now()
                WHERE tenant_id = :tenant_id AND space_id = :space_id AND source_family = :source_family
                """
            ),
            {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "source_family": source_family,
                "active_version": rolled["active_version"],
                "rollback_version": rolled["rollback_version"],
            },
        )
        return {"ok": True, "pointer": rolled, "backend": "pgvector"}
    except Exception:
        return {"ok": False, "reason": "index_not_ready"}


def tenant_pointer_ready(session: Any | None, tenant_id: str) -> bool:
    """True when at least one index pointer for the tenant is ready."""
    tid = (tenant_id or "").strip()
    if not tid:
        return False
    for row in _POINTERS.values():
        if isinstance(row, dict) and row.get("tenant_id") == tid and bool(row.get("ready")):
            return True
    if session is None:
        return False
    try:
        from sqlalchemy import text

        row = session.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM customer_ai_index_pointers
                    WHERE tenant_id = :tenant_id AND ready = true
                )
                """
            ),
            {"tenant_id": tid},
        ).scalar()
        return bool(row)
    except Exception:
        return False


def mark_pointer_not_ready(
    session: Any | None,
    *,
    tenant_id: str,
    source_family: str,
    reason: str = "source_changed",
) -> None:
    for key, row in list(_POINTERS.items()):
        if row.get("tenant_id") == tenant_id and row.get("source_family") == source_family:
            _POINTERS[key] = {**row, "ready": False, "reason": reason}
    if session is None:
        return
    try:
        from sqlalchemy import text

        session.execute(
            text(
                """
                UPDATE customer_ai_index_pointers
                SET ready = false, reason = :reason, updated_at = now()
                WHERE tenant_id = :tenant_id AND source_family = :source_family
                """
            ),
            {"tenant_id": tenant_id, "source_family": source_family, "reason": reason},
        )
    except Exception:
        return


def get_source_pointer_ready(tenant_id: str, family: str) -> dict[str, Any] | None:
    """Public pointer snapshot for a tenant/source_family. None if no pointer known."""
    tid = (tenant_id or "").strip()
    fam = (family or "").strip()
    if not tid or not fam:
        return None
    matches = [
        row
        for row in _POINTERS.values()
        if isinstance(row, dict) and row.get("tenant_id") == tid and row.get("source_family") == fam
    ]
    if not matches:
        return None
    # Prefer a not-ready row when any exist (fail-closed for stale products).
    chosen = next((row for row in matches if row.get("ready") is False), matches[0])
    return {
        "tenant_id": tid,
        "source_family": fam,
        "ready": bool(chosen.get("ready")),
        "reason": str(chosen.get("reason") or ""),
        "active_version": str(chosen.get("active_version") or ""),
        "source_revision": str(chosen.get("source_revision") or ""),
        "record_count": int(chosen.get("record_count") or 0),
    }


def _write_memory(rows: list[dict[str, Any]], vectors: list[list[float]]) -> dict[str, Any]:
    for row, vector in zip(rows, vectors, strict=True):
        tenant_id = str(row.get("tenant_id") or "")
        if not tenant_id:
            continue
        stored = {**row, "embedding": list(vector)}
        bucket = _MEMORY.setdefault(tenant_id, [])
        bucket[:] = [item for item in bucket if item.get("id") != stored.get("id")]
        bucket.append(stored)
    return {"ok": True, "reason": "ok", "count": len(rows), "backend": "memory"}


def _query_memory(
    tenant_id: str,
    space_id: str,
    vector: list[float],
    families: set[str] | None,
    limit: int,
    *,
    active_version: str = "",
) -> StoreQueryResult:
    scored: list[StoreHit] = []
    for row in _MEMORY.get(tenant_id, []):
        if row.get("tenant_id") != tenant_id:
            continue
        if str(row.get("space_id") or "") != space_id:
            continue
        if active_version and str(row.get("index_version") or "") != active_version:
            continue
        if not row.get("visible", True):
            continue
        family = str(row.get("source_family") or "")
        if families is not None and family not in families:
            continue
        score = _cosine(vector, list(row.get("embedding") or []))
        scored.append(
            StoreHit(
                doc_id=str(row.get("id") or ""),
                tenant_id=tenant_id,
                source_family=family,
                source_id=str(row.get("source_id") or ""),
                title=str(row.get("title") or ""),
                search_text=str(row.get("search_text") or ""),
                score=score,
            )
        )
    scored.sort(key=lambda item: (-item.score, item.doc_id))
    return StoreQueryResult(outcome="found" if scored else "not_found", items=scored[:limit])


def _write_sql(session: Any, rows: list[dict[str, Any]], vectors: list[list[float]]) -> dict[str, Any]:
    from sqlalchemy import text

    try:
        for row, vector in zip(rows, vectors, strict=True):
            session.execute(
                text(
                    """
                    INSERT INTO customer_ai_search_documents
                        (id, tenant_id, space_id, source_family, source_id, chunk_id, parent_id,
                         index_version, source_revision, content_hash, title, search_text, visible, embedding)
                    VALUES
                        (:id, :tenant_id, :space_id, :source_family, :source_id, :chunk_id, :parent_id,
                         :index_version, :source_revision, :content_hash, :title, :search_text, :visible,
                         CAST(:embedding AS vector))
                    ON CONFLICT (tenant_id, space_id, source_id, chunk_id, index_version) DO UPDATE SET
                        title = EXCLUDED.title,
                        search_text = EXCLUDED.search_text,
                        visible = EXCLUDED.visible,
                        content_hash = EXCLUDED.content_hash,
                        embedding = EXCLUDED.embedding,
                        updated_at = now()
                    """
                ),
                {
                    "id": str(row.get("id") or ""),
                    "tenant_id": str(row.get("tenant_id") or ""),
                    "space_id": str(row.get("space_id") or ""),
                    "source_family": str(row.get("source_family") or ""),
                    "source_id": str(row.get("source_id") or ""),
                    "chunk_id": str(row.get("chunk_id") or ""),
                    "parent_id": str(row.get("parent_id") or ""),
                    "index_version": str(row.get("index_version") or ""),
                    "source_revision": str(row.get("source_revision") or ""),
                    "content_hash": str(row.get("content_hash") or ""),
                    "title": str(row.get("title") or ""),
                    "search_text": str(row.get("search_text") or ""),
                    "visible": bool(row.get("visible", True)),
                    "embedding": _vector_literal(vector),
                },
            )
        return {"ok": True, "reason": "ok", "count": len(rows), "backend": "pgvector"}
    except Exception as exc:
        import logging

        logging.getLogger("customer_ai.search.store").warning(
            "write_documents sql failed: %s:%s", type(exc).__name__, str(exc)[:200]
        )
        return {"ok": False, "reason": "index_not_ready", "count": 0, "error": f"{type(exc).__name__}:{str(exc)[:160]}"}


def _query_sql(
    session: Any,
    tenant_id: str,
    space_id: str,
    vector: list[float],
    families: set[str] | None,
    limit: int,
    *,
    active_version: str = "",
) -> StoreQueryResult:
    from sqlalchemy import text

    family_list = sorted(families) if families else []
    try:
        rows = session.execute(
            text(
                """
                SELECT id, tenant_id, source_family, source_id, title, search_text,
                       1 - (embedding <=> CAST(:embedding AS vector)) AS score
                FROM customer_ai_search_documents
                WHERE tenant_id = :tenant_id
                  AND space_id = :space_id
                  AND visible = true
                  AND (CAST(:version_len AS int) = 0 OR index_version = :active_version)
                  AND (CAST(:family_count AS int) = 0 OR source_family = ANY(:families))
                ORDER BY embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
                """
            ),
            {
                "tenant_id": tenant_id,
                "space_id": space_id,
                "embedding": _vector_literal(vector),
                "family_count": len(family_list),
                "families": family_list,
                "limit": limit,
                "active_version": active_version,
                "version_len": len(active_version or ""),
            },
        )
    except Exception:
        return StoreQueryResult(outcome="index_not_ready", reason="index_not_ready")
    items: list[StoreHit] = []
    for row in rows:
        mapping = row._mapping if hasattr(row, "_mapping") else None
        data = dict(mapping) if mapping is not None else {}
        if str(data.get("tenant_id") or "") != tenant_id:
            continue
        items.append(
            StoreHit(
                doc_id=str(data.get("id") or ""),
                tenant_id=tenant_id,
                source_family=str(data.get("source_family") or ""),
                source_id=str(data.get("source_id") or ""),
                title=str(data.get("title") or ""),
                search_text=str(data.get("search_text") or ""),
                score=float(data.get("score") or 0.0),
            )
        )
    return StoreQueryResult(outcome="found" if items else "not_found", items=items)
