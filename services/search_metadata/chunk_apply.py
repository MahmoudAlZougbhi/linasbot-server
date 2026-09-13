"""Save-time Luna chunks: rewrite on change, keep on unchanged, delete removed items."""

from __future__ import annotations

from typing import Any

from services.customer_ai.compiler.chunk_store import (
    delete_chunks,
    delete_missing,
    read_chunks,
    write_chunks,
)
from services.customer_ai.compiler.luna_chunker import luna_chunk_prose
from services.customer_ai.compiler.prose import (
    LARGE_TEXT_SECTIONS,
    POLICY_ITEM_ID,
    SECTION_ITEM_ID,
    extract_prose,
    needs_luna_chunks,
)
from services.search_metadata.fingerprint import content_fingerprint, item_id_of
from services.search_metadata.limits import ITEM_LIST_KEYS

_LAST_CHUNK_APPLY: dict[str, Any] = {
    "section": "",
    "generated_ids": [],
    "copied_ids": [],
    "removed_ids": [],
}


def last_chunk_apply_stats() -> dict[str, Any]:
    return dict(_LAST_CHUNK_APPLY)


def apply_luna_chunks(
    section: str,
    payload: dict[str, Any],
    previous: dict[str, Any] | None,
    *,
    tenant_id: str,
) -> dict[str, Any]:
    name = (section or "").strip()
    _LAST_CHUNK_APPLY.update({"section": name, "generated_ids": [], "copied_ids": [], "removed_ids": []})
    if name not in LARGE_TEXT_SECTIONS or not tenant_id.strip() or not isinstance(payload, dict):
        return payload
    keep: set[str] = set()
    generated: list[str] = []
    copied: list[str] = []
    prev = previous if isinstance(previous, dict) else {}
    for key in ITEM_LIST_KEYS:
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        prev_rows = prev.get(key)
        prev_index = _index_items(prev_rows if isinstance(prev_rows, list) else [])
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            item_id = item_id_of(raw)
            if not item_id:
                continue
            keep.add(item_id)
            status = _refresh_item(
                tenant_id=tenant_id,
                section=name,
                item_id=item_id,
                item=raw,
                previous=prev_index.get(item_id),
            )
            if status == "generated":
                generated.append(item_id)
            elif status == "copied":
                copied.append(item_id)
    if name in {"ai_basics", "style"}:
        keep.add(SECTION_ITEM_ID)
        status = _refresh_item(
            tenant_id=tenant_id,
            section=name,
            item_id=SECTION_ITEM_ID,
            item=payload,
            previous=prev if prev else None,
        )
        if status == "generated":
            generated.append(SECTION_ITEM_ID)
        elif status == "copied":
            copied.append(SECTION_ITEM_ID)
    if name in {"branches", "prices"}:
        policy_item = {"policy_text": payload.get("policy_text") or "", "notes": payload.get("notes") or ""}
        prev_policy = {"policy_text": prev.get("policy_text") or "", "notes": prev.get("notes") or ""}
        if needs_luna_chunks(name, policy_item):
            keep.add(POLICY_ITEM_ID)
            status = _refresh_item(
                tenant_id=tenant_id,
                section=name,
                item_id=POLICY_ITEM_ID,
                item=policy_item,
                previous=prev_policy,
            )
            if status == "generated":
                generated.append(POLICY_ITEM_ID)
            elif status == "copied":
                copied.append(POLICY_ITEM_ID)
        else:
            delete_chunks(tenant_id, name, POLICY_ITEM_ID)
    if name == "opening_hours":
        notes_item = {"notes": payload.get("notes") or ""}
        prev_notes = {"notes": prev.get("notes") or ""}
        if needs_luna_chunks(name, notes_item):
            keep.add(SECTION_ITEM_ID)
            status = _refresh_item(
                tenant_id=tenant_id,
                section=name,
                item_id=SECTION_ITEM_ID,
                item=notes_item,
                previous=prev_notes,
            )
            if status == "generated":
                generated.append(SECTION_ITEM_ID)
            elif status == "copied":
                copied.append(SECTION_ITEM_ID)
        else:
            delete_chunks(tenant_id, name, SECTION_ITEM_ID)
    removed = delete_missing(tenant_id, name, keep)
    _LAST_CHUNK_APPLY["generated_ids"] = generated
    _LAST_CHUNK_APPLY["copied_ids"] = copied
    _LAST_CHUNK_APPLY["removed_ids"] = removed
    return payload


def _index_items(rows: list[Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        item_id = item_id_of(raw)
        if item_id:
            out[item_id] = raw
    return out


def _refresh_item(
    *,
    tenant_id: str,
    section: str,
    item_id: str,
    item: dict[str, Any],
    previous: dict[str, Any] | None,
) -> str:
    if not needs_luna_chunks(section, item):
        delete_chunks(tenant_id, section, item_id)
        return "skipped"
    fingerprint = content_fingerprint(item)
    if previous is not None and content_fingerprint(previous) == fingerprint:
        existing = read_chunks(tenant_id, section, item_id)
        if existing and existing.get("fingerprint") == fingerprint:
            return "copied"
    chunks = luna_chunk_prose(
        {
            "section": section,
            "item_id": item_id,
            "content": extract_prose(section, item),
        }
    )
    if not chunks:
        delete_chunks(tenant_id, section, item_id)
        return "skipped"
    write_chunks(tenant_id, section=section, item_id=item_id, fingerprint=fingerprint, chunks=chunks)
    return "generated"
