"""Bounded typed read-only retrieval tools. Tenant comes from server context only."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from services.cm.version_store import load_published_content
from services.customer_reply_v2.flags import max_retrieval_rounds
from services.customer_reply_v2.manifest import FIXED_ANSWER_SECTIONS, manifest_for_retrieval_luna
from services.customer_reply_v2.models import EvidenceRecord, ItemIndexEntry

MAX_ITEMS_PER_SECTION = 80
MAX_ITEMS_PER_READ = 20
MAX_EVIDENCE_CHARS = 12000
TOOL_TIMEOUT_HINT_MS = 5000

RETRIEVAL_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_published_cm_sections",
            "description": "List Published CM sections (manifest). AI Basics/Style are fixed Answer context and not selectable.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_published_cm_items",
            "description": "List item-index metadata for selected selectable Published sections.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["section_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_published_cm_items",
            "description": "Read full allowed contents for exact Published item IDs from the current revision.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["item_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_additional_published_cm_items",
            "description": "Request one additional retrieval round of sections/items. Server refuses after round 2.",
            "parameters": {
                "type": "object",
                "properties": {
                    "section_ids": {"type": "array", "items": {"type": "string"}},
                    "item_ids": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_safe_customer_profile",
            "description": "Read safe persistent customer facts for this conversation (no cross-tenant data).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_dm_context_window",
            "description": "Read the rolling three-hour DM window already loaded by the server.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_comment_post_context",
            "description": "Read comment/post media context for comment events (not DM history).",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_product_by_title",
            "description": "Search tenant product catalog by title (deterministic first, Luna fallback).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_details",
            "description": "Read one product by product_id (tenant-scoped).",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_product_images",
            "description": "List image media_ids for a product (max 3).",
            "parameters": {
                "type": "object",
                "properties": {"product_id": {"type": "string"}},
                "required": ["product_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_product_by_url",
            "description": "Find a product by purchase/info URL (0 AI credits).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_product_by_image",
            "description": "Find product candidates by customer image (vector search; vision rerank if ambiguous).",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_media_id": {"type": "string"},
                    "top_k": {"type": "integer"},
                },
                "required": ["image_media_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_product_context",
            "description": "Read active product context for follow-up questions in this conversation.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_reply_to_product",
            "description": "Resolve product from customer reply-to message id (0 AI credits).",
            "parameters": {
                "type": "object",
                "properties": {"reply_to_message_id": {"type": "string"}},
                "required": ["reply_to_message_id"],
            },
        },
    },
]


@dataclass
class ToolContext:
    tenant_id: str
    published_revision: str
    channel: str
    round_index: int = 1
    customer_profile: dict[str, Any] = field(default_factory=dict)
    dm_window: list[dict[str, str]] = field(default_factory=list)
    comment_context: dict[str, Any] = field(default_factory=dict)
    active_product_id: str | None = None
    conversation_id: str | None = None
    reply_to_message_id: str | None = None
    evidence_acc: list[EvidenceRecord] = field(default_factory=list)
    refused_third_round: bool = False
    audit: list[dict[str, Any]] = field(default_factory=list)


def _label(labels: Any) -> str:
    if isinstance(labels, dict):
        return str(labels.get("en") or labels.get("ar") or labels.get("fr") or "").strip()
    return str(getattr(labels, "en", "") or getattr(labels, "ar", "") or "").strip()


def _iter_section_items(section_id: str, payload: dict[str, Any]) -> list[ItemIndexEntry]:
    entries: list[ItemIndexEntry] = []
    items = payload.get("items")
    if isinstance(items, list):
        for raw in items[:MAX_ITEMS_PER_SECTION]:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or raw.get("qa_group_id") or "").strip()
            if not item_id:
                continue
            title = str(raw.get("title") or _label(raw.get("labels")) or item_id)
            desc = str(raw.get("notes") or raw.get("body") or raw.get("short_introduction") or "")[:240]
            status = str(raw.get("status") or ("active" if raw.get("available", True) else "inactive"))
            if status == "draft":
                continue
            entries.append(
                ItemIndexEntry(
                    item_id=f"{section_id}:{item_id}",
                    section_id=section_id,
                    title=title,
                    short_description=desc,
                    language=str(raw.get("language") or ""),
                    status=status,
                    relations={
                        "service_id": raw.get("service_id"),
                        "linked_service_ids": raw.get("linked_service_ids") or [],
                        "linked_branch_ids": raw.get("linked_branch_ids") or [],
                        "category": raw.get("category"),
                    },
                )
            )
        return entries
    topics = payload.get("topics")
    if isinstance(topics, list):
        for raw in topics[:MAX_ITEMS_PER_SECTION]:
            if not isinstance(raw, dict):
                continue
            item_id = str(raw.get("id") or "").strip()
            if not item_id:
                continue
            entries.append(
                ItemIndexEntry(
                    item_id=f"{section_id}:{item_id}",
                    section_id=section_id,
                    title=_label(raw.get("labels")) or item_id,
                    short_description="restricted topic" if section_id == "restricted" else "",
                    status="active" if raw.get("active", True) else "inactive",
                )
            )
    return entries


def _record_content(section_id: str, raw: dict[str, Any]) -> str:
    if section_id == "faq":
        variants = raw.get("variants") or []
        bits = []
        for v in variants:
            if isinstance(v, dict):
                bits.append(f"Q({v.get('language')}): {v.get('question')} | A: {v.get('answer')}")
        return "\n".join(bits)
    if section_id == "prices":
        return json.dumps(
            {
                "id": raw.get("id"),
                "service_id": raw.get("service_id"),
                "amount": raw.get("amount"),
                "currency": raw.get("currency"),
                "catalog_item_id": raw.get("catalog_item_id"),
            },
            ensure_ascii=False,
        )
    if section_id == "branches":
        return json.dumps(
            {
                "id": raw.get("id"),
                "labels": raw.get("labels"),
                "address": raw.get("address"),
                "hours": raw.get("hours"),
            },
            ensure_ascii=False,
        )
    body = raw.get("body") or raw.get("notes") or ""
    title = raw.get("title") or _label(raw.get("labels"))
    text = f"{title}\n{body}".strip()
    if section_id in {"knowledge", "care"}:
        from services.cm.article_media import format_attachments_block

        att_block = format_attachments_block(list(raw.get("attachments") or []))
        if att_block:
            text = f"{text}\n\n{att_block}".strip() if text else att_block
    return text


def dispatch_retrieval_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Execute a retrieval tool. Ignores any tenant_id the model might pass in args."""
    # Security: model-supplied tenant is ignored.
    args = {k: v for k, v in (args or {}).items() if k != "tenant_id"}
    pointer_sections = None

    def _sections() -> dict[str, dict[str, Any]]:
        nonlocal pointer_sections
        if pointer_sections is None:
            pointer, sections = load_published_content(ctx.tenant_id)
            if pointer.content_version_id != ctx.published_revision:
                raise ValueError("stale_published_revision")
            pointer_sections = sections
        return pointer_sections

    if name == "list_published_cm_sections":
        data = manifest_for_retrieval_luna(ctx.tenant_id)
        ctx.audit.append({"tool": name, "ok": True, "class": "manifest"})
        return {"ok": True, "data": data}

    if name == "list_published_cm_items":
        section_ids = [str(s) for s in (args.get("section_ids") or [])][:12]
        sections = _sections()
        items: list[dict[str, Any]] = []
        rejected: list[str] = []
        for sid in section_ids:
            if sid in FIXED_ANSWER_SECTIONS:
                rejected.append(sid)
                continue
            if sid not in sections:
                rejected.append(sid)
                continue
            for entry in _iter_section_items(sid, sections.get(sid) or {}):
                entry.published_revision = ctx.published_revision
                items.append(
                    {
                        "item_id": entry.item_id,
                        "section_id": entry.section_id,
                        "title": entry.title,
                        "short_description": entry.short_description,
                        "language": entry.language,
                        "status": entry.status,
                        "relations": entry.relations,
                        "published_revision": ctx.published_revision,
                    }
                )
        ctx.audit.append({"tool": name, "ok": True, "class": "item_index", "count": len(items)})
        return {"ok": True, "data": {"items": items, "rejected_section_ids": rejected}}

    if name in {"read_published_cm_items", "request_additional_published_cm_items"}:
        if name == "request_additional_published_cm_items":
            if ctx.round_index >= max_retrieval_rounds():
                ctx.refused_third_round = True
                ctx.audit.append({"tool": name, "ok": False, "class": "round_limit"})
                return {
                    "ok": False,
                    "error": "retrieval_round_limit",
                    "message": f"Server refuses retrieval beyond {max_retrieval_rounds()} rounds.",
                }
            ctx.round_index += 1
            # Also allow section listing as part of round 2
            if args.get("section_ids"):
                listed = dispatch_retrieval_tool("list_published_cm_items", {"section_ids": args["section_ids"]}, ctx)
            else:
                listed = None
        else:
            listed = None

        item_ids = [str(i) for i in (args.get("item_ids") or [])][:MAX_ITEMS_PER_READ]
        sections = _sections()
        # Flatten lookup
        by_id: dict[str, tuple[str, dict[str, Any]]] = {}
        for sid, payload in sections.items():
            if sid in FIXED_ANSWER_SECTIONS:
                continue
            for entry in _iter_section_items(sid, payload or {}):
                raw_items = (payload or {}).get("items") or (payload or {}).get("topics") or []
                raw_match = None
                bare = entry.item_id.split(":", 1)[-1]
                for raw in raw_items:
                    if isinstance(raw, dict) and str(raw.get("id") or raw.get("qa_group_id") or "") == bare:
                        raw_match = raw
                        break
                if raw_match is not None:
                    by_id[entry.item_id] = (sid, raw_match)
                    by_id[bare] = (sid, raw_match)

        evidence: list[dict[str, Any]] = []
        rejected_item_ids: list[str] = []
        chars = 0
        for iid in item_ids:
            if "/" in iid or ".." in iid or iid.startswith("http"):
                rejected_item_ids.append(iid)
                continue
            hit = by_id.get(iid)
            if not hit:
                rejected_item_ids.append(iid)
                continue
            sid, raw = hit
            content = _record_content(sid, raw)
            if chars + len(content) > MAX_EVIDENCE_CHARS:
                rejected_item_ids.append(iid)
                continue
            chars += len(content)
            source_id = iid if ":" in iid else f"{sid}:{iid}"
            rec = EvidenceRecord(
                source_id=source_id,
                section_id=sid,
                title=str(raw.get("title") or _label(raw.get("labels")) or source_id),
                content=content,
                published_revision=ctx.published_revision,
            )
            ctx.evidence_acc.append(rec)
            evidence.append(
                {
                    "source_id": rec.source_id,
                    "section_id": rec.section_id,
                    "title": rec.title,
                    "content": rec.content,
                    "published_revision": rec.published_revision,
                }
            )
        ctx.audit.append({"tool": name, "ok": True, "class": "read_items", "count": len(evidence)})
        out: dict[str, Any] = {"ok": True, "data": {"evidence": evidence, "rejected_item_ids": rejected_item_ids}}
        if listed is not None:
            out["data"]["round_index"] = ctx.round_index
            out["data"]["item_index"] = listed.get("data")
        return out

    if name == "get_safe_customer_profile":
        ctx.audit.append({"tool": name, "ok": True, "class": "profile"})
        return {"ok": True, "data": dict(ctx.customer_profile)}

    if name == "get_dm_context_window":
        ctx.audit.append({"tool": name, "ok": True, "class": "dm_window"})
        return {"ok": True, "data": {"messages": list(ctx.dm_window)}}

    if name == "get_comment_post_context":
        ctx.audit.append({"tool": name, "ok": True, "class": "comment_context"})
        return {"ok": True, "data": dict(ctx.comment_context)}

    product_tools = {
        "search_product_by_title",
        "get_product_details",
        "get_product_images",
        "find_product_by_url",
        "find_product_by_image",
        "get_active_product_context",
        "resolve_reply_to_product",
    }
    if name in product_tools:
        from db.session import whatsapp_session
        from services.products.crv2_tools import (
            crv2_find_product_by_image,
            crv2_find_product_by_url,
            crv2_get_active_product_context,
            crv2_get_product_details,
            crv2_get_product_images,
            crv2_resolve_reply_to_product,
            crv2_search_product_by_title,
        )
        from services.products.media import load_media_bytes

        conversation_id = str(ctx.conversation_id or "").strip() or None
        try:
            with whatsapp_session(require=True) as db:
                if name == "resolve_reply_to_product":
                    data = crv2_resolve_reply_to_product(
                        db,
                        tenant_id=ctx.tenant_id,
                        channel=ctx.channel,
                        reply_to_message_id=str(args.get("reply_to_message_id") or ctx.reply_to_message_id or ""),
                        conversation_id=conversation_id,
                    )
                    if data.get("match"):
                        ctx.active_product_id = str(data["match"].get("id") or "") or None
                elif name == "get_active_product_context":
                    data = crv2_get_active_product_context(
                        db,
                        tenant_id=ctx.tenant_id,
                        conversation_id=conversation_id or "",
                    )
                    if data.get("active_product_id"):
                        ctx.active_product_id = str(data.get("active_product_id") or "") or None
                elif name == "search_product_by_title":
                    title = str(args.get("title") or "").strip()
                    limit = int(args.get("limit") or 5)
                    data = crv2_search_product_by_title(
                        db,
                        tenant_id=ctx.tenant_id,
                        title=title,
                        limit=limit,
                        use_luna_fallback=True,
                        conversation_id=conversation_id,
                    )
                elif name == "get_product_details":
                    product_id = str(args.get("product_id") or ctx.active_product_id or "")
                    data = crv2_get_product_details(
                        db,
                        tenant_id=ctx.tenant_id,
                        product_id=product_id,
                        conversation_id=conversation_id,
                        context_source="active_context",
                    )
                elif name == "get_product_images":
                    product_id = str(args.get("product_id") or ctx.active_product_id or "")
                    data = crv2_get_product_images(
                        db,
                        tenant_id=ctx.tenant_id,
                        product_id=product_id,
                    )
                elif name == "find_product_by_url":
                    data = crv2_find_product_by_url(
                        db,
                        tenant_id=ctx.tenant_id,
                        url=str(args.get("url") or ""),
                        conversation_id=conversation_id,
                    )
                    if data.get("match"):
                        ctx.active_product_id = str(data["match"].get("id") or "") or None
                else:
                    media_id = str(args.get("image_media_id") or "").strip()
                    raw = load_media_bytes(tenant_id=ctx.tenant_id, media_id=media_id)
                    if raw is None:
                        data = {"tool": name, "ok": False, "error": "image_not_found"}
                    else:
                        data = crv2_find_product_by_image(
                            db,
                            tenant_id=ctx.tenant_id,
                            image_bytes=raw,
                            top_k=int(args.get("top_k") or 8),
                            conversation_id=conversation_id,
                        )
                        if data.get("matches"):
                            first = data["matches"][0]
                            ctx.active_product_id = str(first.get("id") or "") or None
        except Exception as exc:
            ctx.audit.append({"tool": name, "ok": False, "class": "products", "error": type(exc).__name__})
            return {"ok": False, "error": "products_tool_failed", "message": type(exc).__name__}
        ctx.audit.append({"tool": name, "ok": True, "class": "products"})
        if ctx.active_product_id and name == "get_product_details":
            data["active_product_context"] = ctx.active_product_id
        return {"ok": True, "data": data}

    ctx.audit.append({"tool": name, "ok": False, "class": "unknown"})
    return {"ok": False, "error": "unknown_tool"}
