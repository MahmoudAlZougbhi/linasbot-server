"""Tenant-scoped product image index — PostgreSQL SoT for multi-server HA."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from db.models.products import ProductImageFingerprint
from services.products.image_fingerprint import (
    combined_image_similarity,
    compute_color_histogram,
    compute_fingerprint,
)
from services.products.media import load_media_bytes

_log = logging.getLogger(__name__)
TOP_K_DEFAULT = 8
SIMILARITY_THRESHOLD = float(os.getenv("LINAS_PRODUCT_IMAGE_SIMILARITY_THRESHOLD", "0.85"))
SCAN_CAP_DEFAULT = 4000
PHASH_PREFIX_LEN = 2


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def upsert_product_image_index(
    session: Session,
    *,
    tenant_id: str,
    product_id: str,
    product_image_id: str,
    media_id: str,
    fingerprint: dict[str, str],
    histogram: list[float],
) -> dict[str, Any]:
    stmt = select(ProductImageFingerprint).where(
        ProductImageFingerprint.tenant_id == tenant_id,
        ProductImageFingerprint.media_id == media_id,
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        row = ProductImageFingerprint(
            id=_uuid(),
            tenant_id=tenant_id,
            product_id=product_id,
            product_image_id=product_image_id,
            media_id=media_id,
            sha256=str(fingerprint.get("sha256") or ""),
            phash=str(fingerprint.get("phash") or ""),
            histogram=list(histogram),
            created_at=_now(),
        )
        session.add(row)
    else:
        row.product_id = product_id
        row.product_image_id = product_image_id
        row.sha256 = str(fingerprint.get("sha256") or "")
        row.phash = str(fingerprint.get("phash") or "")
        row.histogram = list(histogram)
    session.flush()
    return _row_to_entry(row)


def remove_product_from_index(session: Session, *, tenant_id: str, product_id: str) -> None:
    stmt = delete(ProductImageFingerprint).where(
        ProductImageFingerprint.tenant_id == tenant_id,
        ProductImageFingerprint.product_id == product_id,
    )
    session.execute(stmt)
    session.flush()


def remove_media_from_index(session: Session, *, tenant_id: str, media_id: str) -> None:
    stmt = delete(ProductImageFingerprint).where(
        ProductImageFingerprint.tenant_id == tenant_id,
        ProductImageFingerprint.media_id == media_id,
    )
    session.execute(stmt)
    session.flush()


def _row_to_entry(row: ProductImageFingerprint) -> dict[str, Any]:
    return {
        "product_id": row.product_id,
        "product_image_id": row.product_image_id,
        "media_id": row.media_id,
        "sha256": row.sha256,
        "phash": row.phash,
        "histogram": list(row.histogram or []),
    }


def _scan_cap() -> int:
    try:
        return max(32, int(os.getenv("LINAS_PRODUCT_IMAGE_SCAN_CAP", str(SCAN_CAP_DEFAULT))))
    except ValueError:
        return SCAN_CAP_DEFAULT


def _phash_prefix(phash: str) -> str:
    raw = str(phash or "").strip()
    return raw[:PHASH_PREFIX_LEN] if len(raw) >= PHASH_PREFIX_LEN else ""


def find_image_candidates(
    session: Session,
    *,
    tenant_id: str,
    query_bytes: bytes,
    top_k: int = TOP_K_DEFAULT,
    similarity_threshold: float | None = None,
) -> list[dict[str, Any]]:
    threshold = similarity_threshold if similarity_threshold is not None else SIMILARITY_THRESHOLD
    fp = compute_fingerprint(query_bytes)
    hist = compute_color_histogram(query_bytes)
    sha = str(fp.get("sha256") or "")
    prefix = _phash_prefix(str(fp.get("phash") or ""))
    cap = _scan_cap()
    clauses = []
    if sha:
        clauses.append(ProductImageFingerprint.sha256 == sha)
    if prefix:
        clauses.append(ProductImageFingerprint.phash.like(f"{prefix}%"))
    stmt = select(ProductImageFingerprint).where(ProductImageFingerprint.tenant_id == tenant_id)
    if clauses:
        stmt = stmt.where(or_(*clauses))
    stmt = stmt.limit(cap)
    rows = list(session.execute(stmt).scalars().all())
    if len(rows) >= cap:
        _log.warning("product image candidate scan hit cap=%s tenant=%s", cap, tenant_id)
    scored: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        entry = _row_to_entry(row)
        sim = combined_image_similarity(query_fp=fp, query_hist=hist, entry=entry)
        if sim >= threshold:
            scored.append((sim, {**entry, "similarity": sim}))
    scored.sort(key=lambda item: item[0], reverse=True)
    cap_k = min(max(int(top_k), 3), 8)
    return [item[1] for item in scored[:cap_k]]


def build_index_from_media(
    session: Session,
    *,
    tenant_id: str,
    product_id: str,
    product_image_id: str,
    media_id: str,
) -> dict[str, Any] | None:
    content = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
    if content is None:
        return None
    fp = compute_fingerprint(content)
    hist = compute_color_histogram(content)
    return upsert_product_image_index(
        session,
        tenant_id=tenant_id,
        product_id=product_id,
        product_image_id=product_image_id,
        media_id=media_id,
        fingerprint=fp,
        histogram=hist,
    )
