"""Published branch/service/product labels for conversation carry. Never hardcoded tenants."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from services.ai_setup.version_store import PublishedVersionError, load_published_content
from services.brain.normalize import normalize_search_text


def _label_values(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    labels = row.get("labels")
    if isinstance(labels, dict):
        for key in ("en", "ar", "fr", "franco"):
            value = str(labels.get(key) or "").strip()
            if value:
                out.append(value)
    for key in ("title", "name", "id"):
        value = str(row.get(key) or "").strip()
        if value:
            out.append(value)
    for alias in row.get("aliases") or []:
        value = str(alias or "").strip()
        if value:
            out.append(value)
    return list(dict.fromkeys(out))


def _items(sections: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in keys:
        payload = sections.get(key)
        if not isinstance(payload, dict):
            continue
        for group in ("items", "catalog"):
            block = payload.get(group) or []
            rows.extend(row for row in block if isinstance(row, dict))
    return rows


@lru_cache(maxsize=64)
def published_label_index(tenant_id: str) -> dict[str, tuple[tuple[str, str], ...]]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"branches": (), "services": (), "products": ()}
    try:
        _pointer, sections = load_published_content(tid)
    except PublishedVersionError:
        return {"branches": (), "services": (), "products": ()}
    if not isinstance(sections, dict):
        return {"branches": (), "services": (), "products": ()}
    out: dict[str, tuple[tuple[str, str], ...]] = {}
    mapping = {
        "branches": _items(sections, "branches"),
        "services": _items(sections, "prices"),
        "products": _items(sections, "products"),
    }
    for family, rows in mapping.items():
        pairs: list[tuple[str, str]] = []
        for row in rows:
            status = str(row.get("status") or "active").strip().lower()
            if status in {"archived", "draft", "deleted", "inactive", "withdrawn"} or row.get("active") is False:
                continue
            entity_id = str(row.get("id") or "").strip()
            for label in _label_values(row):
                folded = normalize_search_text(label)
                if folded:
                    pairs.append((folded, entity_id or label))
        out[family] = tuple(pairs)
    return out


def match_published_label(text: str, pairs: tuple[tuple[str, str], ...]) -> str:
    hay = normalize_search_text(text)
    if not hay:
        return ""
    hits = [(label, entity_id) for label, entity_id in pairs if label and label in hay]
    if not hits:
        return ""
    hits.sort(key=lambda item: (-len(item[0]), item[1]))
    return hits[0][1]
