"""Product image/link dicts for Terra EVIDENCE and inventory. No bytes."""

from __future__ import annotations

from typing import Any

from services.ai_setup.resource_attachment import customer_resource_descriptors


def _attr(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def product_attachment_dicts(row: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    images = _attr(row, "images", None) or []
    for index, image in enumerate(images):
        mid = str(_attr(image, "media_id") or _attr(image, "id") or "").strip()
        if not mid:
            continue
        out.append(
            {
                "id": mid,
                "kind": "image",
                "title": str(_attr(image, "filename") or mid),
                "status": "active",
                "sort_order": int(_attr(image, "sort_order") or index),
            }
        )
    links = _attr(row, "links", None) or []
    for index, link in enumerate(links):
        url = str(_attr(link, "url") or "").strip()
        lid = str(_attr(link, "id") or url).strip()
        if not url or not lid:
            continue
        out.append(
            {
                "id": lid,
                "kind": "link",
                "title": str(_attr(link, "label") or url),
                "url": url,
                "status": "active",
                "sort_order": 100 + index,
            }
        )
    return out


def product_source_item_id(product_id: str) -> str:
    pid = str(product_id or "").strip()
    if pid.startswith("products:"):
        return pid
    return f"products:{pid}" if pid else ""


def inventory_items_from_product(row: Any) -> list[dict[str, str]]:
    pid = str(_attr(row, "id") or "").strip()
    sid = product_source_item_id(pid)
    if not sid:
        return []
    items: list[dict[str, str]] = []
    for desc in customer_resource_descriptors(product_attachment_dicts(row), source_item_id=sid):
        ref = str(desc.get("resource_ref") or "").strip()
        if not ref:
            continue
        items.append(
            {
                "id": ref,
                "kind": str(desc.get("type") or "file"),
                "title": str(desc.get("title") or ref),
                "source_item_id": sid,
            }
        )
    return items
