"""Tenant-scoped product-image ANN. Postgres uses pgvector HNSW; never a prefix LIKE scan."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.products import ProductImageFingerprint
from services.products.image_phash_vec import l2_sq, phash_to_vec, vec_literal

ANN_FETCH = 24
TOP_K_MAX = 8


def _dialect(session: Session) -> str:
    bind = session.get_bind() if hasattr(session, "get_bind") else None
    return str(getattr(getattr(bind, "dialect", None), "name", "") or "")


def _pgvector(session: Session) -> bool:
    if _dialect(session) != "postgresql":
        return False
    try:
        from services.brain.search.readiness import probe_pgvector

        return probe_pgvector(session)
    except Exception:
        return False


def write_ann_vector(session: Session, row: ProductImageFingerprint) -> None:
    vec = phash_to_vec(str(row.phash or ""))
    row.phash_vec = vec or None
    session.flush()
    if not vec or not _pgvector(session):
        return
    from sqlalchemy import text

    session.execute(
        text(
            """
            UPDATE product_image_fingerprints
               SET phash_embedding = CAST(:embedding AS vector)
             WHERE tenant_id = :tenant_id
               AND id = :id
            """
        ),
        {"embedding": vec_literal(vec), "tenant_id": row.tenant_id, "id": row.id},
    )


def exact_sha256_rows(session: Session, *, tenant_id: str, sha256: str) -> list[ProductImageFingerprint]:
    sha = str(sha256 or "").strip()
    tid = (tenant_id or "").strip()
    if not sha or not tid:
        return []
    stmt = (
        select(ProductImageFingerprint)
        .where(
            ProductImageFingerprint.tenant_id == tid,
            ProductImageFingerprint.sha256 == sha,
        )
        .limit(TOP_K_MAX)
    )
    return list(session.execute(stmt).scalars().all())


def ann_candidate_rows(
    session: Session,
    *,
    tenant_id: str,
    query_vec: list[float],
    fetch: int = ANN_FETCH,
) -> list[ProductImageFingerprint]:
    tid = (tenant_id or "").strip()
    cap = min(max(int(fetch), 1), ANN_FETCH)
    if not tid or len(query_vec) != 64:
        return []
    if _pgvector(session):
        return _ann_pg(session, tenant_id=tid, query_vec=query_vec, fetch=cap)
    if _dialect(session) == "sqlite":
        return _ann_sqlite_test(session, tenant_id=tid, query_vec=query_vec, fetch=cap)
    return []


def backfill_missing_ann(session: Session, *, tenant_id: str, limit: int = 200) -> dict[str, Any]:
    """Idempotent tenant-scoped batch. Does not run on a customer turn."""
    tid = (tenant_id or "").strip()
    cap = min(max(int(limit), 1), 500)
    if not tid:
        return {"ok": False, "updated": 0}
    stmt = (
        select(ProductImageFingerprint)
        .where(
            ProductImageFingerprint.tenant_id == tid,
            ProductImageFingerprint.phash_vec.is_(None),
        )
        .limit(cap)
    )
    updated = 0
    for row in session.execute(stmt).scalars().all():
        write_ann_vector(session, row)
        updated += 1
    session.flush()
    return {"ok": True, "updated": updated, "tenant_id": tid}


def _ann_pg(session: Session, *, tenant_id: str, query_vec: list[float], fetch: int) -> list[ProductImageFingerprint]:
    from sqlalchemy import text

    rows = session.execute(
        text(
            """
            SELECT id
              FROM product_image_fingerprints
             WHERE tenant_id = :tenant_id
               AND phash_embedding IS NOT NULL
             ORDER BY phash_embedding <=> CAST(:embedding AS vector)
             LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "embedding": vec_literal(query_vec), "limit": fetch},
    )
    ids = [str(row[0]) for row in rows if row and row[0]]
    return _hydrate_ids(session, tenant_id=tenant_id, ids=ids)


def _ann_sqlite_test(
    session: Session,
    *,
    tenant_id: str,
    query_vec: list[float],
    fetch: int,
) -> list[ProductImageFingerprint]:
    stmt = select(ProductImageFingerprint).where(ProductImageFingerprint.tenant_id == tenant_id)
    scored: list[tuple[float, ProductImageFingerprint]] = []
    for row in session.execute(stmt).scalars().all():
        vec = list(row.phash_vec or [])
        if len(vec) != 64:
            vec = phash_to_vec(str(row.phash or ""))
        if len(vec) != 64:
            continue
        scored.append((l2_sq(query_vec, vec), row))
    scored.sort(key=lambda item: item[0])
    return [row for _dist, row in scored[:fetch]]


def _hydrate_ids(session: Session, *, tenant_id: str, ids: list[str]) -> list[ProductImageFingerprint]:
    keep = [item for item in ids if item]
    if not keep:
        return []
    stmt = select(ProductImageFingerprint).where(
        ProductImageFingerprint.tenant_id == tenant_id,
        ProductImageFingerprint.id.in_(keep),
    )
    by_id = {row.id: row for row in session.execute(stmt).scalars().all()}
    return [by_id[item] for item in keep if item in by_id]
