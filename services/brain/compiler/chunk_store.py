"""Per-item save-time chunk sidecars. Overwrite on save; delete when the item is gone."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.ai_setup.atomic_io import atomic_write_json, read_json_object
from services.ai_setup.paths import tenant_cm_root

CHUNK_STORE_VERSION = "luna.chunk.v1"


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
    data = read_chunks(tenant_id, section, item_id)
    if not data:
        return ()
    rows = data.get("chunks")
    if not isinstance(rows, list):
        return ()
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


def delete_chunks(tenant_id: str, section: str, item_id: str) -> None:
    path = chunk_path(tenant_id, section, item_id)
    if path.exists():
        path.unlink()


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
