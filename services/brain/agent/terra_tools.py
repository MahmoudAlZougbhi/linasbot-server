"""OpenAI function schemas for the single Terra customer session."""

from __future__ import annotations

import json
from typing import Any

from services.brain.agent.terra_request_round import REQUEST_TOOLS, openai_request_tools
from services.brain.tools.registry import ACTION_TOOLS, READ_TOOLS, UNSUPPORTED_TOOLS

TOOL_USE_RULES = (
    "You may call allowlisted tools when needed, then write the customer-facing reply in this "
    "same turn. Do not wait for a later model. After tool RECEIPTS return, author the reply "
    "yourself from EVIDENCE, RECEIPTS, IDENTITY, STYLE, and POLICY.\n"
    "Call request tools to start/update/submit/cancel ORDER or APPOINTMENT, or escalate_to_human "
    "for Live Chat. Call no_request_action when this inbound is another topic.\n"
    "On a public comment, do not start ORDER/APPOINTMENT and do not collect PII; invite DM in "
    "your own words. Never invent facts missing from EVIDENCE/RECEIPTS."
)

_READ_EXTRA = {
    "get_service": "Look up a published service by query or id.",
    "search_services": "Search published services.",
    "get_product": "Look up a published product by query or id.",
    "search_products": "Search published products.",
    "get_price": "Look up a published price.",
    "get_branch": "Look up a published branch.",
    "get_branch_hours": "Look up published branch hours.",
    "get_faq": "Look up a published FAQ.",
    "get_published_knowledge": "Look up published knowledge.",
    "resolve_resource": "Resolve a published resource_ref.",
    "check_setup_resources": "List published setup resources for this evidence (kinds/counts).",
    "list_resources": "Alias of check_setup_resources.",
    "get_contact": "Look up published contact details.",
}

_ACTION_EXTRA = {
    "send_resource": "Queue a published resource to send. Never claim send without a RECEIPT.",
}


def _schema(name: str, description: str, extra_props: dict[str, Any] | None = None) -> dict[str, Any]:
    props = {
        "task_id": {"type": "string"},
        "customer_text": {"type": "string"},
        "query": {"type": "string"},
        **(extra_props or {}),
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": props, "additionalProperties": True},
        },
    }


def openai_customer_tools() -> list[dict[str, Any]]:
    """Request schemas plus remaining allowlisted read/action tools."""
    out = list(openai_request_tools())
    seen = set(REQUEST_TOOLS)
    extra_props = {
        "item_id": {"type": "string"},
        "resource_ref": {"type": "string"},
        "resource_id": {"type": "string"},
        "kind": {"type": "string"},
        "source_ids": {"type": "array", "items": {"type": "string"}},
    }
    for name, description in {**_READ_EXTRA, **_ACTION_EXTRA}.items():
        if name in seen or name in UNSUPPORTED_TOOLS:
            continue
        if name not in READ_TOOLS and name not in ACTION_TOOLS:
            continue
        out.append(_schema(name, description, extra_props))
        seen.add(name)
    return out


def parse_tool_calls(message: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_calls = getattr(message, "tool_calls", None)
    if raw_calls is None and isinstance(message, dict):
        raw_calls = message.get("tool_calls")
    for item in list(raw_calls or []):
        if isinstance(item, dict):
            fn = item.get("function") or {}
            name = str((fn.get("name") if isinstance(fn, dict) else "") or "")
            raw = str((fn.get("arguments") if isinstance(fn, dict) else "") or "{}")
            call_id = str(item.get("id") or "")
        else:
            fn = getattr(item, "function", None)
            name = str(getattr(fn, "name", "") or "")
            raw = str(getattr(fn, "arguments", "") or "{}")
            call_id = str(getattr(item, "id", "") or "")
        try:
            args = json.loads(raw) if raw else {}
        except Exception:
            args = {}
        if not isinstance(args, dict):
            args = {}
        if not name or name in UNSUPPORTED_TOOLS:
            continue
        if name not in READ_TOOLS and name not in ACTION_TOOLS:
            continue
        rows.append({"id": call_id or f"call_{len(rows) + 1}", "tool": name, "args": args})
    return rows


def assistant_tool_message(content: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": content or None,
        "tool_calls": [
            {
                "id": row["id"],
                "type": "function",
                "function": {"name": row["tool"], "arguments": json.dumps(row["args"], ensure_ascii=False)},
            }
            for row in calls
        ],
    }
