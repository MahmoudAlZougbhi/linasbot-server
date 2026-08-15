"""Product image index stub — checksum + perceptual-hash path for Phase 1.

Phase 2 adds real vision rerank; Phase 1 stores fingerprints and exact checksum matches.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from services.products.media import load_media_bytes, load_media_meta
from services.products.paths import tenant_products_root

logger = logging.getLogger(__name__)

TOP_K_DEFAULT = 10


def _index_path(tenant_id: str) -> Path:
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
    entries = data.get("entries")
    if not isinstance(entries, list):
        data["entries"] = []
    return data


def _save_index(tenant_id: str, data: dict[str, Any]) -> None:
    path = _index_path(tenant_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def compute_fingerprint(content: bytes) -> dict[str, str]:
    """Checksum + stub perceptual hash (Phase 2 replaces phash_stub with real pHash)."""
    sha = hashlib.sha256(content).hexdigest()
    # Stub: deterministic 16-hex slice — not a real perceptual hash yet.
    phash_stub = hashlib.sha256(content[: min(len(content), 4096)]).hexdigest()[:16]
    return {"sha256": sha, "phash_stub": phash_stub}


def upsert_product_image_index(
    *,
    tenant_id: str,
    product_id: str,
    media_id: str,
) -> dict[str, str] | None:
    content = load_media_bytes(tenant_id=tenant_id, media_id=media_id)
    if content is None:
        return None
    fp = compute_fingerprint(content)
    data = _load_index(tenant_id)
    entries = [e for e in data.get("entries", []) if e.get("media_id") != media_id]
    entries.append(
        {
            "product_id": product_id,
            "media_id": media_id,
            "sha256": fp["sha256"],
            "phash_stub": fp["phash_stub"],
        }
    )
    data["entries"] = entries
    _save_index(tenant_id, data)
    return fp


def remove_product_from_index(*, tenant_id: str, product_id: str) -> None:
    data = _load_index(tenant_id)
    data["entries"] = [e for e in data.get("entries", []) if e.get("product_id") != product_id]
    _save_index(tenant_id, data)


def find_image_candidates(
    *,
    tenant_id: str,
    query_bytes: bytes,
    top_k: int = TOP_K_DEFAULT,
) -> list[dict[str, Any]]:
    """Top-K candidates by exact checksum; phash_stub reserved for Phase 2 rerank."""
    fp = compute_fingerprint(query_bytes)
    data = _load_index(tenant_id)
    exact = [
        e
        for e in data.get("entries", [])
        if e.get("sha256") == fp["sha256"]
    ]
    if exact:
        return exact[:top_k]

    # Stub path: no vision rerank — return empty; Phase 2 fills via phash distance.
    return []
