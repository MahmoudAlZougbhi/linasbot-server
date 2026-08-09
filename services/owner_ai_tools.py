"""Typed, authorized tools for the owner Linas AI System Copilot.

LLM / heuristic output never writes storage directly — tools call service APIs only.
CM writes go through propose → approve (human confirmation).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.owner_ai_tools_base import ToolResult
from services.owner_ai_tools_read import (
    tool_help,
    tool_read_account_summary,
    tool_read_cm,
    tool_read_dashboard_metrics,
    tool_read_integrations,
    tool_read_jobs_errors,
    tool_read_profile,
    tool_read_scheduled_posts,
    tool_read_subscription,
    tool_read_usage,
    tool_validate_cm,
)
from services.owner_ai_tools_write import (
    tool_approve_cm_patch,
    tool_propose_cm_patch,
    tool_publish_cm,
    tool_update_profile,
)

TOOL_HANDLERS: dict[str, Callable[..., Awaitable[ToolResult]]] = {
    "help": tool_help,
    "read_profile": tool_read_profile,
    "read_account_summary": tool_read_account_summary,
    "read_cm": tool_read_cm,
    "validate_cm": tool_validate_cm,
    "propose_cm_patch": tool_propose_cm_patch,
    "approve_cm_patch": tool_approve_cm_patch,
    "publish_cm": tool_publish_cm,
    "read_usage": tool_read_usage,
    "read_subscription": tool_read_subscription,
    "read_integrations": tool_read_integrations,
    "read_dashboard_metrics": tool_read_dashboard_metrics,
    "read_scheduled_posts": tool_read_scheduled_posts,
    "read_jobs_errors": tool_read_jobs_errors,
    "update_profile": tool_update_profile,
}

HIGH_IMPACT_TOOLS: frozenset[str] = frozenset(
    {
        "publish_cm",
        "approve_cm_patch",
        "propose_cm_patch",
    }
)


def list_tool_names() -> list[str]:
    return sorted(TOOL_HANDLERS.keys())


async def dispatch_tool(
    name: str,
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    args: dict[str, Any] | None = None,
    confirmed: bool = False,
) -> ToolResult:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return ToolResult(ok=False, name=name, data={}, error=f"Unknown tool: {name}")
    a = dict(args or {})
    if name == "help":
        return await handler(tenant_id=tenant_id, role=role, query=str(a.get("query") or ""))
    if name == "read_profile":
        return await handler(tenant_id=tenant_id, role=role, user_id=user_id)
    if name == "read_account_summary":
        return await handler(tenant_id=tenant_id, role=role, user_id=user_id)
    if name == "read_cm":
        return await handler(tenant_id=tenant_id, role=role, section=a.get("section"))
    if name == "propose_cm_patch":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            section=str(a.get("section") or ""),
            patch=dict(a.get("patch") or {}),
        )
    if name == "approve_cm_patch":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            proposal_id=str(a.get("proposal_id") or ""),
            confirmed=confirmed,
        )
    if name == "publish_cm":
        return await handler(tenant_id=tenant_id, role=role, confirmed=confirmed)
    if name == "update_profile":
        return await handler(tenant_id=tenant_id, role=role, user_id=user_id, updates=a)
    if name == "read_dashboard_metrics":
        return await handler(tenant_id=tenant_id, role=role, user_id=user_id)
    # Generic read tools
    return await handler(tenant_id=tenant_id, role=role)
