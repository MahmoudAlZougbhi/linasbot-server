"""Register Requests capture tool for Customer Reply AI when capture is active."""

from __future__ import annotations

from typing import Any

from services.requests.ai_tool import (
    CREATE_CUSTOMER_REQUEST_TOOL_NAME,
    CREATE_CUSTOMER_REQUEST_TOOL_SCHEMA,
    AiToolContext,
    execute_create_customer_request,
    tools_for_tenant,
)

__all__ = [
    "CREATE_CUSTOMER_REQUEST_TOOL_NAME",
    "CREATE_CUSTOMER_REQUEST_TOOL_SCHEMA",
    "customer_reply_capture_tools",
    "dispatch_capture_tool",
]


def customer_reply_capture_tools(tenant_id: str | None) -> list[dict[str, Any]]:
    """Tool schemas for Answer/customer loops — empty when capture inactive."""
    return tools_for_tenant(tenant_id)


def dispatch_capture_tool(
    name: str,
    args: dict[str, Any],
    ctx: AiToolContext,
    *,
    session: Any,
) -> dict[str, Any]:
    if name != CREATE_CUSTOMER_REQUEST_TOOL_NAME:
        return {"ok": False, "error": "unknown_tool"}
    return execute_create_customer_request(args, ctx, session=session)
