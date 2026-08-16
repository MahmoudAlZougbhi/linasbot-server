"""Shared AI Setup resource attachment model (image/video/file/link).

Bytes stay in the existing CM media store. This model is metadata only.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RESOURCE_TYPES = ("image", "video", "file", "link")
ResourceKind = Literal["image", "video", "file", "link"]
ResourceStatus = Literal["draft", "active", "inactive", "deleted"]
CUSTOMER_VISIBLE_STATUSES = frozenset({"active"})


class ResourceAttachment(BaseModel):
    """Universal resource on a publishable AI Setup node."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    id: str
    kind: ResourceKind = "file"
    title: str = ""
    description: str = ""
    caption: str = ""
    mime: str = ""
    filename: str = ""
    size: int = Field(default=0, ge=0)
    url: str = ""
    duration_seconds: int | None = Field(default=None, ge=0)
    status: ResourceStatus = "active"
    sort_order: int = 0


def resource_title(att: dict[str, Any] | ResourceAttachment) -> str:
    raw = att.model_dump(mode="json") if isinstance(att, ResourceAttachment) else dict(att)
    title = str(raw.get("title") or "").strip()
    if title:
        return title
    return str(raw.get("filename") or raw.get("id") or "").strip()


def resource_description(att: dict[str, Any] | ResourceAttachment) -> str:
    raw = att.model_dump(mode="json") if isinstance(att, ResourceAttachment) else dict(att)
    desc = str(raw.get("description") or "").strip()
    if desc:
        return desc
    return str(raw.get("caption") or "").strip()


def is_customer_visible_resource(att: dict[str, Any] | ResourceAttachment) -> bool:
    raw = att.model_dump(mode="json") if isinstance(att, ResourceAttachment) else dict(att)
    status = str(raw.get("status") or "active").strip().lower() or "active"
    if status not in CUSTOMER_VISIBLE_STATUSES:
        return False
    kind = str(raw.get("kind") or "").strip().lower()
    return kind in RESOURCE_TYPES and bool(str(raw.get("id") or "").strip())


def resource_summary(attachments: list[Any] | None) -> dict[str, Any]:
    counts = {"images": 0, "videos": 0, "files": 0, "links": 0}
    for raw in attachments or []:
        att = raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw
        if not isinstance(att, dict) or not is_customer_visible_resource(att):
            continue
        kind = str(att.get("kind") or "file")
        if kind == "image":
            counts["images"] += 1
        elif kind == "video":
            counts["videos"] += 1
        elif kind == "link":
            counts["links"] += 1
        else:
            counts["files"] += 1
    total = sum(counts.values())
    return {**counts, "has_resources": total > 0}


def customer_resource_descriptors(
    attachments: list[Any] | None,
    *,
    source_item_id: str,
) -> list[dict[str, str]]:
    """Tera-facing descriptors: no bytes, storage keys, or private URLs."""
    out: list[dict[str, str]] = []
    visible = [(raw.model_dump(mode="json") if hasattr(raw, "model_dump") else raw) for raw in (attachments or [])]
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for index, att in enumerate(visible):
        if not isinstance(att, dict) or not is_customer_visible_resource(att):
            continue
        ranked.append((int(att.get("sort_order") or 0), index, att))
    ranked.sort(key=lambda row: (row[0], row[1]))
    for _order, _index, att in ranked:
        kind = str(att.get("kind") or "file")
        out.append(
            {
                "resource_ref": str(att.get("id") or ""),
                "type": kind,
                "title": resource_title(att),
                "description": resource_description(att),
                "source_item_id": source_item_id,
            }
        )
    return out


def validate_owner_resource_fields(*, title: str, description: str, kind: str, url: str = "") -> dict[str, Any]:
    if kind not in RESOURCE_TYPES:
        return {"ok": False, "error": "invalid_resource_type"}
    if not str(title or "").strip():
        return {"ok": False, "error": "title_required"}
    if not str(description or "").strip():
        return {"ok": False, "error": "description_required"}
    if kind == "link" and not str(url or "").strip():
        return {"ok": False, "error": "url_required"}
    return {"ok": True}
