"""Structured ATTACHMENTS block Terra always sees on retrieved CM cards."""

from __future__ import annotations

from typing import Any

from services.ai_setup.resource_attachment import customer_resource_descriptors, resource_summary


def format_resource_ref_block(
    attachments: list[Any] | None,
    *,
    source_item_id: str,
) -> str:
    sid = str(source_item_id or "").strip()
    rows = customer_resource_descriptors(attachments, source_item_id=sid)
    if not sid or not rows:
        return ""
    counts = resource_summary(attachments)
    lines = [f"ATTACHMENTS source_item_id={sid}"]
    for row in rows:
        title = str(row.get("title") or "").replace("\n", " ").strip()
        lines.append(f"- resource_ref={row['resource_ref']} kind={row.get('type') or 'file'} title={title}")
    lines.append(
        "summary "
        f"images={int(counts.get('images') or 0)} "
        f"videos={int(counts.get('videos') or 0)} "
        f"links={int(counts.get('links') or 0)} "
        f"files={int(counts.get('files') or 0)}"
    )
    return "\n".join(lines)


def merge_body_with_attachments(body: str, block: str) -> str:
    text = str(body or "").strip()
    extra = str(block or "").strip()
    if not extra:
        return text
    if extra in text:
        return text
    if not text:
        return extra
    return f"{text}\n{extra}"


def product_attachment_dicts(row: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    images = getattr(row, "images", None) if not isinstance(row, dict) else row.get("images")
    for index, image in enumerate(images or []):
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
    links = getattr(row, "links", None) if not isinstance(row, dict) else row.get("links")
    for index, link in enumerate(links or []):
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


def _attr(row: Any, key: str, default: Any = "") -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)
