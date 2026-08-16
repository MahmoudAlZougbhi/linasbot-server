"""Bounded typed read-only retrieval tools. Tenant comes from server context only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.cm.resource_attachment import resource_summary
from services.cm.setup_resources import descriptors_for_item
from services.cm.version_store import load_published_content
from services.customer_reply_v2.flags import max_retrieval_rounds
from services.customer_reply_v2.manifest import FIXED_ANSWER_SECTIONS, manifest_for_retrieval_luna
from services.customer_reply_v2.models import EvidenceRecord
from services.customer_reply_v2.operational_titles import (
    TITLE_PAGE_SIZE,
    collect_operational_titles,
    page_operational_titles,
)
from services.customer_reply_v2.retrieval_item_index import (
    MAX_EVIDENCE_CHARS,
    MAX_ITEMS_PER_READ,
    MAX_ITEMS_PER_SECTION,
    iter_section_items,
    label_of,
    raw_rows_for_section,
    record_content,
)
from services.customer_reply_v2.retrieval_product_dispatch import PRODUCT_TOOL_NAMES, dispatch_product_tool
from services.customer_reply_v2.retrieval_request_dispatch import (
    REQUEST_GRAPH_TOOL_NAMES,
    compiled_graph_content,
    dispatch_request_graph_tool,
)
from services.customer_reply_v2.retrieval_tool_schemas import RETRIEVAL_TOOL_SCHEMAS

TOOL_TIMEOUT_HINT_MS = 5000

__all__ = [
    "MAX_EVIDENCE_CHARS",
    "MAX_ITEMS_PER_READ",
    "MAX_ITEMS_PER_SECTION",
    "RETRIEVAL_TOOL_SCHEMAS",
    "TOOL_TIMEOUT_HINT_MS",
    "ToolContext",
    "dispatch_retrieval_tool",
]


@dataclass
class ToolContext:
    tenant_id: str
    published_revision: str
    channel: str
    round_index: int = 1
    customer_profile: dict[str, Any] = field(default_factory=dict)
    dm_window: list[dict[str, Any]] = field(default_factory=list)
    comment_context: dict[str, Any] = field(default_factory=dict)
    channel_metadata: dict[str, Any] = field(default_factory=dict)
    active_product_id: str | None = None
    conversation_id: str | None = None
    reply_to_message_id: str | None = None
    evidence_acc: list[EvidenceRecord] = field(default_factory=list)
    refused_third_round: bool = False
    audit: list[dict[str, Any]] = field(default_factory=list)
    customer_id: str = ""


def _load_sections(ctx: ToolContext) -> dict[str, dict[str, Any]]:
    pointer, sections = load_published_content(ctx.tenant_id)
    if pointer.content_version_id != ctx.published_revision:
        raise ValueError("stale_published_revision")
    return sections


def _item_lookup(sections: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    by_id: dict[str, tuple[str, dict[str, Any]]] = {}
    for sid, payload in sections.items():
        if sid in FIXED_ANSWER_SECTIONS:
            continue
        for entry in iter_section_items(sid, payload or {}):
            raw_match = None
            bare = entry.item_id.split(":", 1)[-1]
            for raw in raw_rows_for_section(payload or {}):
                if str(raw.get("id") or raw.get("qa_group_id") or "") == bare:
                    raw_match = raw
                    break
            if raw_match is not None:
                by_id[entry.item_id] = (sid, raw_match)
                by_id[bare] = (sid, raw_match)
    return by_id


def _read_items(ctx: ToolContext, args: dict[str, Any], listed: dict[str, Any] | None) -> dict[str, Any]:
    item_ids = [str(i) for i in (args.get("item_ids") or [])][:MAX_ITEMS_PER_READ]
    sections = _load_sections(ctx)
    by_id = _item_lookup(sections)
    evidence: list[dict[str, Any]] = []
    rejected: list[dict[str, str]] = []
    chars = 0
    for iid in item_ids:
        if "/" in iid or ".." in iid or iid.startswith("http"):
            rejected.append({"item_id": iid, "reason": "invalid_id"})
            continue
        hit = by_id.get(iid)
        if not hit:
            rejected.append({"item_id": iid, "reason": "not_found"})
            continue
        sid, raw = hit
        content = record_content(sid, raw)
        if sid == "requests_appointments":
            content = compiled_graph_content(
                tenant_id=ctx.tenant_id,
                source_item_id=str(raw.get("id") or "").strip(),
                fallback=content,
            )
        if len(content) > MAX_EVIDENCE_CHARS:
            rejected.append({"item_id": iid, "reason": "file_too_large"})
            ctx.audit.append(
                {"tool": "read_published_cm_items", "ok": False, "class": "file_too_large", "item_id": iid}
            )
            continue
        if chars + len(content) > MAX_EVIDENCE_CHARS:
            rejected.append({"item_id": iid, "reason": "evidence_budget_exceeded"})
            continue
        chars += len(content)
        source_id = iid if ":" in iid else f"{sid}:{iid}"
        rec = EvidenceRecord(
            source_id=source_id,
            section_id=sid,
            title=str(raw.get("title") or raw.get("name") or label_of(raw.get("labels")) or source_id),
            content=content,
            published_revision=ctx.published_revision,
            allowed_resources=descriptors_for_item(source_item_id=source_id, item=raw),
        )
        ctx.evidence_acc.append(rec)
        evidence.append(
            {
                "source_id": rec.source_id,
                "section_id": rec.section_id,
                "title": rec.title,
                "content": rec.content,
                "resource_summary": resource_summary(list(raw.get("attachments") or [])),
                "published_revision": rec.published_revision,
                "path": f"{sid}/{source_id.split(':', 1)[-1]}",
            }
        )
    ctx.audit.append({"tool": "read_published_cm_items", "ok": True, "class": "read_items", "count": len(evidence)})
    out: dict[str, Any] = {
        "ok": True,
        "data": {
            "evidence": evidence,
            "rejected_item_ids": [row["item_id"] for row in rejected],
            "rejected": rejected,
            "silent_truncation": False,
        },
    }
    if listed is not None:
        out["data"]["round_index"] = ctx.round_index
        out["data"]["item_index"] = listed.get("data")
    return out


def dispatch_retrieval_tool(name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    """Execute a retrieval tool. Ignores any tenant_id the model might pass in args."""
    args = {k: v for k, v in (args or {}).items() if k != "tenant_id"}

    if name == "list_published_cm_sections":
        data = manifest_for_retrieval_luna(ctx.tenant_id)
        ctx.audit.append({"tool": name, "ok": True, "class": "manifest"})
        return {"ok": True, "data": data}

    if name == "list_operational_titles":
        sections = _load_sections(ctx)
        titles = collect_operational_titles(sections)
        page = page_operational_titles(
            titles,
            offset=int(args.get("offset") or 0),
            limit=int(args.get("limit") or TITLE_PAGE_SIZE),
        )
        ctx.audit.append({"tool": name, "ok": True, "class": "operational_titles", "count": page["returned"]})
        return {"ok": True, "data": page}

    if name == "list_published_cm_items":
        section_ids = [str(s) for s in (args.get("section_ids") or [])][:12]
        sections = _load_sections(ctx)
        items: list[dict[str, Any]] = []
        rejected: list[str] = []
        for sid in section_ids:
            if sid in FIXED_ANSWER_SECTIONS:
                rejected.append(sid)
                continue
            if sid not in sections:
                rejected.append(sid)
                continue
            for entry in iter_section_items(sid, sections.get(sid) or {}):
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
                        "resource_summary": dict(entry.resource_summary or {}),
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
            listed = (
                dispatch_retrieval_tool("list_published_cm_items", {"section_ids": args["section_ids"]}, ctx)
                if args.get("section_ids")
                else None
            )
        else:
            listed = None
        return _read_items(ctx, args, listed)

    if name == "get_safe_customer_profile":
        ctx.audit.append({"tool": name, "ok": True, "class": "profile"})
        return {"ok": True, "data": dict(ctx.customer_profile)}

    if name == "get_dm_context_window":
        ctx.audit.append({"tool": name, "ok": True, "class": "dm_window"})
        return {"ok": True, "data": {"messages": list(ctx.dm_window)}}

    if name == "get_comment_post_context":
        ctx.audit.append({"tool": name, "ok": True, "class": "comment_context"})
        return {"ok": True, "data": dict(ctx.comment_context)}

    if name in PRODUCT_TOOL_NAMES:
        return dispatch_product_tool(name, args, ctx)

    if name in REQUEST_GRAPH_TOOL_NAMES:
        return dispatch_request_graph_tool(name, args, ctx)

    ctx.audit.append({"tool": name, "ok": False, "class": "unknown"})
    return {"ok": False, "error": "unknown_tool"}
