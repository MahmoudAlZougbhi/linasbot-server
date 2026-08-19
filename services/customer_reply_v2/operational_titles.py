"""Operational title manifest for Luna (no AI Basics/Style bodies, no product catalog)."""

from __future__ import annotations

from typing import Any

from services.cm.resource_attachment import resource_summary
from services.customer_reply_v2.comment_rule_select import is_luna_selectable_comment_rule
from services.customer_reply_v2.manifest import FIXED_ANSWER_SECTIONS

TITLE_PAGE_SIZE = 80
INLINE_TITLE_CHAR_BUDGET = 12000
EXCLUDED_TITLE_SECTIONS = frozenset(FIXED_ANSWER_SECTIONS)


def _status_of(raw: dict[str, Any]) -> str:
    if raw.get("enabled") is False or raw.get("active") is False:
        return "inactive"
    status = str(raw.get("status") or "").strip().lower()
    if status:
        return status
    return "active"


def _walk_nodes(
    *,
    section_id: str,
    rows: list[Any],
    parent_id: str | None,
    path_prefix: str,
    depth: int,
    sort_base: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, dict):
            continue
        item_id = str(raw.get("id") or raw.get("qa_group_id") or "").strip()
        if not item_id:
            continue
        status = _status_of(raw)
        if status in {"draft", "deleted", "archived"}:
            continue
        from services.search_metadata.luna_titles import luna_title_fields

        fields = luna_title_fields(raw)
        source_id = f"{section_id}:{item_id}"
        path = f"{path_prefix}/{item_id}" if path_prefix else f"{section_id}/{item_id}"
        children_rows = raw.get("children")
        nested_items = children_rows if isinstance(children_rows, list) else []
        child_count = len([c for c in nested_items if isinstance(c, dict)])
        if section_id == "comments" and not is_luna_selectable_comment_rule(raw):
            continue
        out.append(
            {
                "id": source_id,
                "title": fields["title"],
                "original_title": fields["original_title"],
                "ai_search_title": fields["ai_search_title"],
                "ai_search_description": fields["ai_search_description"],
                "type": section_id,
                "parent_id": parent_id,
                "path": path,
                "depth": depth,
                "status": "active" if status in {"", "active"} else status,
                "child_count": child_count,
                "description": fields["description"],
                "linked_entity_type": raw.get("linked_entity_type") or raw.get("entity_type"),
                "scope": raw.get("post_id") or raw.get("scope"),
                "sort_order": sort_base + index,
                "resource_summary": resource_summary(list(raw.get("attachments") or [])),
            }
        )
        if nested_items:
            out.extend(
                _walk_nodes(
                    section_id=section_id,
                    rows=nested_items,
                    parent_id=source_id,
                    path_prefix=path,
                    depth=depth + 1,
                    sort_base=0,
                )
            )
    return out


def collect_operational_titles(sections: dict[str, Any]) -> list[dict[str, Any]]:
    titles: list[dict[str, Any]] = []
    for section_id, payload in (sections or {}).items():
        if section_id in EXCLUDED_TITLE_SECTIONS or not isinstance(payload, dict):
            continue
        rows: list[Any] = []
        seen_ids: set[str] = set()
        for key in ("items", "topics", "rules", "catalog"):
            maybe = payload.get(key)
            if not isinstance(maybe, list) or not maybe:
                continue
            for row in maybe:
                if not isinstance(row, dict):
                    continue
                rid = str(row.get("id") or row.get("qa_group_id") or "").strip()
                if rid and rid in seen_ids:
                    continue
                if rid:
                    seen_ids.add(rid)
                rows.append(row)
        titles.extend(
            _walk_nodes(
                section_id=section_id,
                rows=rows,
                parent_id=None,
                path_prefix=section_id,
                depth=0,
                sort_base=0,
            )
        )
    return titles


def page_operational_titles(
    titles: list[dict[str, Any]],
    *,
    offset: int = 0,
    limit: int = TITLE_PAGE_SIZE,
) -> dict[str, Any]:
    start = max(0, int(offset))
    size = max(1, min(int(limit or TITLE_PAGE_SIZE), TITLE_PAGE_SIZE))
    page = titles[start : start + size]
    next_offset = start + len(page)
    return {
        "titles": page,
        "offset": start,
        "limit": size,
        "returned": len(page),
        "total": len(titles),
        "has_more": next_offset < len(titles),
        "next_offset": next_offset if next_offset < len(titles) else None,
    }


def inline_titles_for_luna(titles: list[dict[str, Any]]) -> dict[str, Any]:
    """Send all titles when they fit; otherwise first page plus explicit pagination."""
    blob = str(titles)
    if len(titles) <= TITLE_PAGE_SIZE and len(blob) <= INLINE_TITLE_CHAR_BUDGET:
        return {
            "operational_titles": titles,
            "operational_title_count": len(titles),
            "operational_titles_has_more": False,
            "operational_titles_truncated": False,
        }
    page = page_operational_titles(titles, offset=0, limit=TITLE_PAGE_SIZE)
    return {
        "operational_titles": page["titles"],
        "operational_title_count": page["total"],
        "operational_titles_has_more": True,
        "operational_titles_truncated": False,
        "operational_titles_next_offset": page["next_offset"],
        "note": "More operational titles exist. Call list_operational_titles to page the rest. Do not assume missing titles are unimportant.",
    }
