"""Published AI Setup resource lookup over existing CM attachments.

No second attachment store. Customer AI sees only published + active + current
revision + same tenant. Storage keys, bytes, and private URLs stay server-side.
"""

from __future__ import annotations

from typing import Any

from services.cm.resource_attachment import (
    customer_resource_descriptors,
    is_customer_visible_resource,
    resource_summary,
    validate_owner_resource_fields,
)
from services.cm.version_store import PublishedVersionError, load_published_content

_ROW_KEYS = ("items", "topics", "rules", "catalog")


def _as_dict(raw: Any) -> dict[str, Any] | None:
    if hasattr(raw, "model_dump"):
        dumped = raw.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else None
    return raw if isinstance(raw, dict) else None


def _walk_rows(section_id: str, payload: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []

    def _visit(rows: list[Any], *, parent_path: str) -> None:
        for raw in rows:
            item = _as_dict(raw)
            if item is None:
                continue
            item_id = str(item.get("id") or item.get("qa_group_id") or "").strip()
            if not item_id:
                continue
            source_id = f"{section_id}:{item_id}"
            out.append((source_id, item))
            children = item.get("children")
            if isinstance(children, list):
                _visit(children, parent_path=source_id)

    if not isinstance(payload, dict):
        return out
    for key in _ROW_KEYS:
        rows = payload.get(key)
        if isinstance(rows, list) and rows:
            _visit(rows, parent_path=section_id)
    return out


def iter_published_source_items(sections: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    items: list[tuple[str, dict[str, Any]]] = []
    for section_id, payload in (sections or {}).items():
        if not isinstance(payload, dict):
            continue
        items.extend(_walk_rows(str(section_id), payload))
    return items


def summary_for_item(item: dict[str, Any]) -> dict[str, Any]:
    return resource_summary(list(item.get("attachments") or []))


def descriptors_for_item(*, source_item_id: str, item: dict[str, Any]) -> list[dict[str, str]]:
    return customer_resource_descriptors(list(item.get("attachments") or []), source_item_id=source_item_id)


def index_published_resources(tenant_id: str) -> dict[str, dict[str, Any]]:
    """Map resource_ref -> record for the current published revision only."""
    pointer, sections = load_published_content(tenant_id)
    revision = pointer.content_version_id
    index: dict[str, dict[str, Any]] = {}
    for source_id, item in iter_published_source_items(sections):
        section_id = source_id.split(":", 1)[0]
        for att_raw in list(item.get("attachments") or []):
            att = _as_dict(att_raw)
            if att is None or not is_customer_visible_resource(att):
                continue
            ref = str(att.get("id") or "").strip()
            if not ref:
                continue
            index[ref] = {
                "resource_ref": ref,
                "tenant_id": tenant_id,
                "source_type": "ai_setup_item",
                "source_item_id": source_id,
                "source_section": section_id,
                "source_revision": revision,
                "resource_type": str(att.get("kind") or "file"),
                "title": str(att.get("title") or att.get("filename") or ref),
                "description": str(att.get("description") or att.get("caption") or ""),
                "mime_type": str(att.get("mime") or ""),
                "external_url": str(att.get("url") or "") if str(att.get("kind") or "") == "link" else "",
                "storage_key": ref if str(att.get("kind") or "") != "link" else "",
                "status": str(att.get("status") or "active"),
                "sort_order": int(att.get("sort_order") or 0),
            }
    return index


def resolve_published_resource(
    *,
    tenant_id: str,
    resource_ref: str,
    allowed_source_ids: list[str] | None = None,
) -> dict[str, Any]:
    ref = str(resource_ref or "").strip()
    if not ref:
        return {"ok": False, "error": "resource_ref_required"}
    try:
        index = index_published_resources(tenant_id)
    except PublishedVersionError as exc:
        return {"ok": False, "error": "published_content_unavailable", "detail": str(exc)}
    record = index.get(ref)
    if record is None:
        return {"ok": False, "error": "resource_not_found"}
    if str(record.get("tenant_id") or "") != tenant_id:
        return {"ok": False, "error": "tenant_isolation"}
    allowed = {str(s).strip() for s in (allowed_source_ids or []) if str(s).strip()}
    if allowed and str(record.get("source_item_id") or "") not in allowed:
        return {"ok": False, "error": "resource_not_on_selected_file"}
    return {"ok": True, "resource": record}


__all__ = [
    "descriptors_for_item",
    "index_published_resources",
    "iter_published_source_items",
    "resolve_published_resource",
    "summary_for_item",
    "validate_owner_resource_fields",
]
