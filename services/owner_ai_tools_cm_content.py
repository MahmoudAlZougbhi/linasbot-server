"""Owner Copilot tools for full CM article/FAQ read + surgical upsert proposals.

AI Setup “files” in this product are CM draft section records — especially
knowledge/care ``ArticleRecord`` rows (migrated from legacy knowledge JSON files)
and FAQ ``FaqRecord`` rows. Full bodies live in draft JSON; inventory APIs are
metadata-only. These tools give the model bounded list/read access and reuse the
existing propose → approve → ``apply_section_patch`` write spine.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from modules.api_security import resolve_permissions
from services.owner_ai_tools_base import ToolResult

ARTICLE_SECTIONS = frozenset({"knowledge", "care"})
# Keep one body chunk comfortably under the model tool-result budget (24k envelope).
DEFAULT_BODY_CHUNK = 12000
MAX_BODY_CHUNK = 20000
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 100
# When a whole section JSON fits, read_cm returns the full payload.
FULL_SECTION_JSON_BUDGET = 18000
DEFAULT_ITEMS_PAGE = 25
MAX_ITEMS_PAGE = 50


def _require(role: str, permission: str) -> None:
    if not resolve_permissions(role, None).get(permission):
        raise PermissionError(f"Missing permission: {permission}")


def _normalize_section(section: str) -> str:
    return (section or "").strip().replace("-", "_")


def _article_meta(item: dict[str, Any], *, section: str) -> dict[str, Any]:
    body = str(item.get("body") or "")
    raw_atts = item.get("attachments")
    attachments: list[Any] = list(raw_atts) if isinstance(raw_atts, list) else []
    captions: list[str] = []
    for row in attachments:
        if not isinstance(row, dict):
            continue
        cap = str(row.get("caption") or "").strip()
        name = str(row.get("filename") or row.get("id") or "").strip()
        if cap or name:
            captions.append(f"{name}: {cap}" if cap else name)
    return {
        "section": section,
        "id": str(item.get("id") or ""),
        "title": str(item.get("title") or ""),
        "status": str(item.get("status") or ""),
        "source_filename": item.get("source_filename"),
        "tags": list(item.get("tags") or []) if isinstance(item.get("tags"), list) else [],
        "language": str(item.get("language") or ""),
        "audience": str(item.get("audience") or ""),
        "category": str(item.get("category") or ""),
        "body_chars": len(body),
        "attachment_count": len(attachments),
        "attachment_captions": captions[:12],
    }


def _faq_meta(item: dict[str, Any]) -> dict[str, Any]:
    raw_variants = item.get("variants")
    variants: list[Any] = list(raw_variants) if isinstance(raw_variants, list) else []
    langs = []
    for v in variants:
        if isinstance(v, dict) and v.get("language"):
            langs.append(str(v["language"]))
    return {
        "qa_group_id": str(item.get("qa_group_id") or ""),
        "status": str(item.get("status") or ""),
        "tags": list(item.get("tags") or []) if isinstance(item.get("tags"), list) else [],
        "source_language": item.get("source_language"),
        "reviewed": bool(item.get("reviewed")),
        "variant_languages": langs,
        "variant_count": len(variants),
    }


def _load_section_items(tenant_id: str, section: str) -> tuple[list[dict[str, Any]], dict[str, Any], Any]:
    from services.cm.storage import get_draft

    env = get_draft(section, tenant_id=tenant_id, create_default=True)
    payload = dict(env.payload) if isinstance(env.payload, dict) else {}
    raw = payload.get("items")
    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for row in raw:
            if isinstance(row, dict):
                items.append(dict(row))
    return items, payload, env


def _fit_items_page(
    base_fields: dict[str, Any],
    page: list[Any],
    *,
    budget: int = FULL_SECTION_JSON_BUDGET,
) -> list[Any]:
    """Shrink an items page until the JSON envelope fits the tool-result budget."""
    fitted = list(page)
    while fitted:
        candidate = {**base_fields, "items": fitted}
        enc = json.dumps(candidate, ensure_ascii=False, default=str)
        if len(enc) <= budget or len(fitted) == 1:
            return fitted
        fitted = fitted[: max(1, len(fitted) // 2)]
    return fitted


def compact_read_cm_draft(
    payload: dict[str, Any],
    *,
    section: str,
    items_offset: int = 0,
    items_limit: int | None = None,
) -> dict[str, Any]:
    """Return full section bodies — never summary-only stubs for items.

    Small sections return the complete payload. Large ``items`` lists return a
    page of **full** item bodies and ``items_next_offset`` until complete.
    knowledge/care/faq may also use list/read item tools for per-entry chunking
    of very long article bodies.
    """
    keys = sorted(payload.keys())
    encoded = json.dumps(payload, ensure_ascii=False, default=str)
    off = max(0, int(items_offset or 0))
    if len(encoded) <= FULL_SECTION_JSON_BUDGET and off == 0 and items_limit is None:
        return {
            "section": section,
            "payload_keys": keys,
            "payload": payload,
            "payload_complete": True,
        }

    raw_items = payload.get("items")
    items: list[Any] = list(raw_items) if isinstance(raw_items, list) else []
    base_fields = {k: v for k, v in payload.items() if k != "items"}

    if items:
        lim = min(MAX_ITEMS_PAGE, max(1, int(items_limit or DEFAULT_ITEMS_PAGE)))
        page = _fit_items_page(base_fields, items[off : off + lim])
        lim = max(1, len(page))
        next_off = off + len(page)
        complete = next_off >= len(items)
        out_payload = {**base_fields, "items": page}
        hint = (
            "Paginated full section items. Continue read_cm with the same section and "
            "items_offset=items_next_offset until payload_complete is true."
        )
        if section in ARTICLE_SECTIONS:
            hint = (
                "Paginated full article bodies. Continue with items_offset when "
                "payload_complete is false, or use list_cm_articles/read_cm_article "
                "for per-article body_offset chunking of very long bodies."
            )
        elif section == "faq":
            hint = (
                "Paginated full FAQ groups. Continue with items_offset when "
                "payload_complete is false, or use list_cm_faq/read_cm_faq."
            )
        return {
            "section": section,
            "payload_keys": keys,
            "payload": out_payload,
            "payload_complete": complete,
            "items_total": len(items),
            "items_offset": off,
            "items_limit": lim,
            "items_returned": len(page),
            "items_next_offset": None if complete else next_off,
            "payload_chars": len(encoded),
            "hint": hint,
        }

    # Rare: no items list but still over budget (huge string fields). Chunk JSON text.
    lim = FULL_SECTION_JSON_BUDGET
    chunk = encoded[off : off + lim]
    complete = off + len(chunk) >= len(encoded)
    return {
        "section": section,
        "payload_keys": keys,
        "payload_json_chunk": chunk,
        "payload_complete": complete,
        "payload_chars": len(encoded),
        "payload_offset": off,
        "payload_limit": lim,
        "payload_next_offset": None if complete else off + len(chunk),
        "hint": (
            "Section JSON chunked. Continue read_cm with items_offset=payload_next_offset "
            "until payload_complete is true, then parse the concatenated JSON."
        ),
    }


async def tool_list_cm_articles(
    *,
    tenant_id: str,
    role: str,
    section: str = "knowledge",
    status: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_LIST_LIMIT,
) -> ToolResult:
    _require(role, "contentManagers")
    name = _normalize_section(section) or "knowledge"
    if name not in ARTICLE_SECTIONS:
        return ToolResult(
            ok=False,
            name="list_cm_articles",
            data={},
            error=f"section must be one of {sorted(ARTICLE_SECTIONS)}",
        )
    items, _payload, env = _load_section_items(tenant_id, name)
    status_f = (status or "").strip().lower() or None
    filtered = [row for row in items if not status_f or str(row.get("status") or "").lower() == status_f]
    off = max(0, int(offset or 0))
    lim = min(MAX_LIST_LIMIT, max(1, int(limit or DEFAULT_LIST_LIMIT)))
    page = filtered[off : off + lim]
    return ToolResult(
        ok=True,
        name="list_cm_articles",
        data={
            "section": name,
            "revision": getattr(env, "revision", None),
            "total": len(filtered),
            "offset": off,
            "limit": lim,
            "has_more": off + lim < len(filtered),
            "articles": [_article_meta(row, section=name) for row in page],
        },
    )


async def tool_read_cm_article(
    *,
    tenant_id: str,
    role: str,
    section: str,
    article_id: str,
    body_offset: int = 0,
    body_limit: int = DEFAULT_BODY_CHUNK,
) -> ToolResult:
    _require(role, "contentManagers")
    name = _normalize_section(section)
    if name not in ARTICLE_SECTIONS:
        return ToolResult(
            ok=False,
            name="read_cm_article",
            data={},
            error=f"section must be one of {sorted(ARTICLE_SECTIONS)}",
        )
    aid = (article_id or "").strip()
    if not aid:
        return ToolResult(ok=False, name="read_cm_article", data={}, error="article_id required")

    items, _payload, env = _load_section_items(tenant_id, name)
    match = next((row for row in items if str(row.get("id") or "") == aid), None)
    if match is None:
        return ToolResult(
            ok=False,
            name="read_cm_article",
            data={"section": name, "article_id": aid},
            error="article_not_found",
        )

    body = str(match.get("body") or "")
    off = max(0, int(body_offset or 0))
    lim = min(MAX_BODY_CHUNK, max(1, int(body_limit or DEFAULT_BODY_CHUNK)))
    chunk = body[off : off + lim]
    article_out = {k: v for k, v in match.items() if k != "body"}
    article_out["body"] = chunk
    article_out["body_chars"] = len(body)
    article_out["body_offset"] = off
    article_out["body_limit"] = lim
    article_out["body_complete"] = off + len(chunk) >= len(body)
    article_out["body_next_offset"] = off + len(chunk) if off + len(chunk) < len(body) else None

    return ToolResult(
        ok=True,
        name="read_cm_article",
        data={
            "section": name,
            "revision": getattr(env, "revision", None),
            "article": article_out,
        },
    )


async def tool_list_cm_faq(
    *,
    tenant_id: str,
    role: str,
    status: str | None = None,
    offset: int = 0,
    limit: int = DEFAULT_LIST_LIMIT,
) -> ToolResult:
    _require(role, "contentManagers")
    items, _payload, env = _load_section_items(tenant_id, "faq")
    status_f = (status or "").strip().lower() or None
    filtered = [row for row in items if not status_f or str(row.get("status") or "").lower() == status_f]
    off = max(0, int(offset or 0))
    lim = min(MAX_LIST_LIMIT, max(1, int(limit or DEFAULT_LIST_LIMIT)))
    page = filtered[off : off + lim]
    return ToolResult(
        ok=True,
        name="list_cm_faq",
        data={
            "section": "faq",
            "revision": getattr(env, "revision", None),
            "total": len(filtered),
            "offset": off,
            "limit": lim,
            "has_more": off + lim < len(filtered),
            "items": [_faq_meta(row) for row in page],
        },
    )


async def tool_read_cm_faq(
    *,
    tenant_id: str,
    role: str,
    qa_group_id: str,
) -> ToolResult:
    _require(role, "contentManagers")
    gid = (qa_group_id or "").strip()
    if not gid:
        return ToolResult(ok=False, name="read_cm_faq", data={}, error="qa_group_id required")
    items, _payload, env = _load_section_items(tenant_id, "faq")
    match = next((row for row in items if str(row.get("qa_group_id") or "") == gid), None)
    if match is None:
        return ToolResult(
            ok=False,
            name="read_cm_faq",
            data={"qa_group_id": gid},
            error="faq_not_found",
        )
    return ToolResult(
        ok=True,
        name="read_cm_faq",
        data={
            "section": "faq",
            "revision": getattr(env, "revision", None),
            "item": match,
        },
    )

# Public re-exports (LOC split; upsert module imports helpers defined above).
from services.owner_ai_tools_cm_upsert import (  # noqa: E402, F401
    _build_article_upsert,
    _build_faq_upsert,
    tool_propose_cm_article_upsert,
    tool_propose_cm_faq_upsert,
)
