"""Tenant-scoped product image index — exact sha256 + ANN, hydrate by id."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from db.models.products import ProductImageFingerprint
from services.products.image_ann import ANN_FETCH, TOP_K_MAX, ann_candidate_rows, exact_sha256_rows, write_ann_vector
from services.products.image_fingerprint import (
    combined_image_similarity,
    compute_color_histogram,
    compute_fingerprint,
)
from services.products.image_phash_vec import phash_to_vec
from services.products.media import load_media_bytes

TOP_K_DEFAULT = 8
SIMILARITY_THRESHOLD = float(os.getenv("LINAS_PRODUCT_IMAGE_SIMILARITY_THRESHOLD", "0.85"))


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
    write_ann_vector(session, row)
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
    cap_k = min(max(int(top_k), 1), TOP_K_MAX)
    scored: dict[str, tuple[float, dict[str, Any]]] = {}
    for row in exact_sha256_rows(session, tenant_id=tenant_id, sha256=str(fp.get("sha256") or "")):
        entry = {**_row_to_entry(row), "similarity": 1.0}
        scored[row.media_id] = (1.0, entry)
    query_vec = phash_to_vec(str(fp.get("phash") or ""))
    for row in ann_candidate_rows(session, tenant_id=tenant_id, query_vec=query_vec, fetch=ANN_FETCH):
        if row.media_id in scored:
            continue
        entry = _row_to_entry(row)
        sim = combined_image_similarity(query_fp=fp, query_hist=hist, entry=entry)
        if sim >= threshold:
            scored[row.media_id] = (sim, {**entry, "similarity": sim})
    ranked = sorted(scored.values(), key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:cap_k]]


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
