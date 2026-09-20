"""Per-item save-time chunk sidecars. Overwrite on save; delete when the item is gone."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from services.ai_setup.atomic_io import atomic_write_json, read_json_object
from services.ai_setup.paths import tenant_cm_root

CHUNK_STORE_VERSION = "luna.chunk.v1"
_CHUNK_LOCK = threading.Lock()
_CHUNK_CACHE: dict[tuple[str, str, str], tuple[str, ...]] = {}
_CHUNK_MAX = 256


def invalidate_chunk_cache(tenant_id: str | None = None) -> None:
    tid = (tenant_id or "").strip()
    with _CHUNK_LOCK:
        if not tid:
            _CHUNK_CACHE.clear()
            return
        for key in [k for k in _CHUNK_CACHE if k[0] == tid]:
            _CHUNK_CACHE.pop(key, None)


def save_chunks_dir(tenant_id: str) -> Path:
    return tenant_cm_root(tenant_id) / "luna_chunks"


def _safe_part(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in (value or "").strip())[:80] or "_"


def chunk_path(tenant_id: str, section: str, item_id: str) -> Path:
    return save_chunks_dir(tenant_id) / _safe_part(section) / f"{_safe_part(item_id)}.json"


def read_chunks(tenant_id: str, section: str, item_id: str) -> dict[str, Any] | None:
    path = chunk_path(tenant_id, section, item_id)
    if not path.exists():
        return None
    try:
        data = read_json_object(path)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def chunk_texts(tenant_id: str, section: str, item_id: str) -> tuple[str, ...]:
    key = (tenant_id, section, item_id)
    with _CHUNK_LOCK:
        hit = _CHUNK_CACHE.get(key)
        if hit is not None:
            return hit
    data = read_chunks(tenant_id, section, item_id)
    if not data:
        texts: tuple[str, ...] = ()
    else:
        rows = data.get("chunks")
        texts = _texts_from_rows(rows if isinstance(rows, list) else [])
    with _CHUNK_LOCK:
        if len(_CHUNK_CACHE) >= _CHUNK_MAX:
            _CHUNK_CACHE.pop(next(iter(_CHUNK_CACHE)))
        _CHUNK_CACHE[key] = texts
    return texts


def _texts_from_rows(rows: list[object]) -> tuple[str, ...]:
    texts: list[str] = []
    for raw in rows:
        if isinstance(raw, dict):
            text = str(raw.get("text") or "").strip()
            heading = str(raw.get("heading") or "").strip()
            blob = "\n".join(p for p in (heading, text) if p)
            if blob:
                texts.append(blob)
    return tuple(texts)


def write_chunks(
    tenant_id: str,
    *,
    section: str,
    item_id: str,
    fingerprint: str,
    chunks: list[dict[str, str]],
) -> None:
    path = chunk_path(tenant_id, section, item_id)
    payload = {
        "version": CHUNK_STORE_VERSION,
        "section": section,
        "item_id": item_id,
        "fingerprint": fingerprint,
        "chunks": [
            {
                "chunk_id": f"{item_id}:c{index}",
                "heading": str(row.get("heading") or ""),
                "text": str(row.get("text") or ""),
            }
            for index, row in enumerate(chunks, 1)
            if str(row.get("text") or "").strip()
        ],
    }
    atomic_write_json(path, payload)
    with _CHUNK_LOCK:
        _CHUNK_CACHE.pop((tenant_id, section, item_id), None)


def delete_chunks(tenant_id: str, section: str, item_id: str) -> None:
    path = chunk_path(tenant_id, section, item_id)
    if path.exists():
        path.unlink()
    with _CHUNK_LOCK:
        _CHUNK_CACHE.pop((tenant_id, section, item_id), None)


def delete_missing(tenant_id: str, section: str, keep_ids: set[str]) -> list[str]:
    root = save_chunks_dir(tenant_id) / _safe_part(section)
    if not root.exists():
        return []
    removed: list[str] = []
    for path in root.glob("*.json"):
        item_id = path.stem
        if item_id in keep_ids:
            continue
        path.unlink()
        removed.append(item_id)
    return removed
