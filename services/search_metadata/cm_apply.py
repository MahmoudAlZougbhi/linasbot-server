"""Apply save-time Luna metadata to one CM section payload (changed items only)."""

from __future__ import annotations

from typing import Any

from services.search_metadata.fingerprint import content_fingerprint, item_id_of
from services.search_metadata.generate import SearchMetadata, generate_search_metadata
from services.search_metadata.item_content import save_time_item_content
from services.search_metadata.limits import ITEM_LIST_KEYS, METADATA_SECTIONS
from services.search_metadata.luna_titles import original_title_of

_LAST_APPLY: dict[str, Any] = {
    "section": "",
    "generated_ids": [],
    "copied_ids": [],
    "removed_ids": [],
}


def last_cm_apply_stats() -> dict[str, Any]:
    return dict(_LAST_APPLY)


def _index_items(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key in ITEM_LIST_KEYS:
        rows = (payload or {}).get(key)
        if not isinstance(rows, list):
            continue
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item_id = item_id_of(raw)
            if item_id:
                out[item_id] = raw
    return out


def _copy_meta(src: dict[str, Any] | None, dest: dict[str, Any]) -> None:
    if not src:
        dest["ai_search_title"] = str(dest.get("ai_search_title") or "")
        dest["ai_search_description"] = str(dest.get("ai_search_description") or "")
        return
    dest["ai_search_title"] = str(src.get("ai_search_title") or "")
    dest["ai_search_description"] = str(src.get("ai_search_description") or "")


def _write_meta(dest: dict[str, Any], meta: SearchMetadata) -> None:
    dest["ai_search_title"] = meta.title
    dest["ai_search_description"] = meta.description


def enrich_section_payload(
    section: str,
    payload: dict[str, Any],
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate English metadata for new/changed items only. Unchanged items keep prior metadata.

    Deleted items disappear with the payload (no orphan store). Legacy items without metadata
    are left empty until that item itself changes — no tenant-wide backfill.
    """
    name = (section or "").strip()
    _LAST_APPLY.update({"section": name, "generated_ids": [], "copied_ids": [], "removed_ids": []})
    if name not in METADATA_SECTIONS or not isinstance(payload, dict):
        return payload
    prev_index = _index_items(previous if isinstance(previous, dict) else {})
    generated: list[str] = []
    copied: list[str] = []
    current_ids: set[str] = set()
    out = dict(payload)
    for key in ITEM_LIST_KEYS:
        rows = out.get(key)
        if not isinstance(rows, list):
            continue
        next_rows: list[Any] = []
        for raw in rows:
            if not isinstance(raw, dict):
                next_rows.append(raw)
                continue
            item = dict(raw)
            item_id = item_id_of(item)
            if not item_id:
                next_rows.append(item)
                continue
            current_ids.add(item_id)
            prev = prev_index.get(item_id)
            if prev is not None and content_fingerprint(item) == content_fingerprint(prev):
                _copy_meta(prev, item)
                copied.append(item_id)
                next_rows.append(item)
                continue
            meta = generate_search_metadata(
                {
                    "kind": "cm",
                    "section": name,
                    "item_id": item_id,
                    "original_title": original_title_of(item),
                    "content": save_time_item_content(name, item),
                    "include_keywords": False,
                }
            )
            _write_meta(item, meta)
            generated.append(item_id)
            next_rows.append(item)
        out[key] = next_rows
    _LAST_APPLY["generated_ids"] = generated
    _LAST_APPLY["copied_ids"] = copied
    _LAST_APPLY["removed_ids"] = sorted(set(prev_index) - current_ids)
    return out
