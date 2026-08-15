"""Tenant-scoped product image index — checksum, phash, local vector search."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from services.products.image_fingerprint import (
    combined_image_similarity,
    compute_color_histogram,
    compute_fingerprint,
)
from services.products.media import load_media_bytes

TOP_K_DEFAULT = 8
SIMILARITY_THRESHOLD = float(os.getenv("LINAS_PRODUCT_IMAGE_SIMILARITY_THRESHOLD", "0.85"))


def _index_path(tenant_id: str) -> Path:
    from services.products.paths import tenant_products_root

    return tenant_products_root(tenant_id) / "image_index.json"


def _load_index(tenant_id: str) -> dict[str, Any]:
    path = _index_path(tenant_id)
    if not path.is_file():
        return {"entries": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"entries": []}
    if not isinstance(data, dict):
        return {"entries": []}
    if not isinstance(data.get("entries"), list):
        data["entries"] = []
    return data


def _save_index(tenant_id: str, data: dict[str, Any]) -> None:
    path = _index_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def upsert_product_image_index(
    *,
    tenant_id: str,
    product_id: str,
    product_image_id: str,
    media_id: str,
    fingerprint: dict[str, str],
    histogram: list[float],
) -> dict[str, Any]:
    data = _load_index(tenant_id)
    entries = [
        e
        for e in data.get("entries", [])
        if e.get("media_id") != media_id and e.get("product_image_id") != product_image_id
    ]
    entry = {
        "product_id": product_id,
        "product_image_id": product_image_id,
        "media_id": media_id,
        "sha256": fingerprint.get("sha256"),
        "phash": fingerprint.get("phash"),
        "histogram": histogram,
    }
    entries.append(entry)
    data["entries"] = entries
    _save_index(tenant_id, data)
    return entry


def remove_product_from_index(*, tenant_id: str, product_id: str) -> None:
    data = _load_index(tenant_id)
    data["entries"] = [e for e in data.get("entries", []) if e.get("product_id") != product_id]
    _save_index(tenant_id, data)


def find_image_candidates(
    *,
    tenant_id: str,
    query_bytes: bytes,
    top_k: int = TOP_K_DEFAULT,
    similarity_threshold: float | None = None,
) -> list[dict[str, Any]]:
    threshold = similarity_threshold if similarity_threshold is not None else SIMILARITY_THRESHOLD
    fp = compute_fingerprint(query_bytes)
    hist = compute_color_histogram(query_bytes)
    scored: list[tuple[float, dict[str, Any]]] = []
    for entry in _load_index(tenant_id).get("entries", []):
        sim = combined_image_similarity(query_fp=fp, query_hist=hist, entry=entry)
        if sim >= threshold:
            scored.append((sim, {**entry, "similarity": sim}))
    scored.sort(key=lambda item: item[0], reverse=True)
    cap = min(max(int(top_k), 3), 8)
    return [item[1] for item in scored[:cap]]


def build_index_from_media(
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
        tenant_id=tenant_id,
        product_id=product_id,
        product_image_id=product_image_id,
        media_id=media_id,
        fingerprint=fp,
        histogram=hist,
    )
