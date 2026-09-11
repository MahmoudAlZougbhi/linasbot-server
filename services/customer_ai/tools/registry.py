"""Tenant-scoped Customer Brain tool registry. Unknown tools are rejected."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.tools import actions as action_tools
from services.customer_ai.tools import reads as read_tools

READ_TOOLS = frozenset(
    {
        "get_service",
        "search_services",
        "get_product",
        "search_products",
        "get_price",
        "get_branch",
        "get_branch_hours",
        "get_faq",
        "get_published_knowledge",
        "resolve_resource",
        "get_contact",
        "get_request_state",
    }
)

ACTION_TOOLS = frozenset(
    {
        "escalate_to_human",
        "start_request",
        "update_request_draft",
        "submit_request",
        "cancel_request",
        "send_resource",
    }
)

UNSUPPORTED_TOOLS = frozenset({"get_availability", "create_booking", "request_booking"})


def list_tools() -> dict[str, list[str]]:
    return {
        "read": sorted(READ_TOOLS),
        "action": sorted(ACTION_TOOLS),
        "unsupported": sorted(UNSUPPORTED_TOOLS),
    }


async def execute_tool(name: str, args: dict[str, Any] | None, turn: CustomerTurn) -> dict[str, Any]:
    tool = (name or "").strip()
    payload = dict(args or {})
    if tool in UNSUPPORTED_TOOLS:
        return {"ok": False, "error": "unsupported_tool", "unsupported": True, "data": None}
    if tool not in READ_TOOLS and tool not in ACTION_TOOLS:
        return {"ok": False, "error": "unknown_tool", "data": None}
    if not turn.tenant_id:
        return {"ok": False, "error": "missing_tenant", "data": None}
    if tool in READ_TOOLS:
        return await read_tools.run_read(tool, payload, turn)
    return await action_tools.run_action(tool, payload, turn)
