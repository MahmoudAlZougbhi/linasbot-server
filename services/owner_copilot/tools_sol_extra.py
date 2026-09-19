"""Sol extra tools: pending batch approve, comment rules, connected posts, tenant dig."""

from __future__ import annotations

from typing import Any

from services.owner_copilot.tools_base import ToolResult


async def dispatch_sol_extra_tool(
    name: str,
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    args: dict[str, Any],
    confirmed: bool,
) -> ToolResult | None:
    if name == "list_pending_cm_proposals":
        from services.owner_copilot.cm_multi_approve import tool_list_pending_cm_proposals

        return tool_list_pending_cm_proposals(tenant_id=tenant_id, user_id=user_id, role=role)
    if name == "approve_cm_batch":
        from services.owner_copilot.cm_multi_approve import tool_approve_cm_batch

        raw = args.get("proposal_ids") or []
        ids = [str(x) for x in raw] if isinstance(raw, list) else []
        if not ids and args.get("proposal_id"):
            ids = [str(args["proposal_id"])]
        return await tool_approve_cm_batch(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            proposal_ids=ids,
            confirmed=confirmed,
        )
    if name == "propose_comment_rule":
        from services.owner_copilot.tools_comment_rules import tool_propose_comment_rule

        return await tool_propose_comment_rule(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            args=args,
        )
    if name == "list_connected_posts":
        from services.owner_copilot.tools_comment_rules import tool_list_connected_posts

        return await tool_list_connected_posts(
            tenant_id=tenant_id,
            role=role,
            platform=str(args.get("platform") or ""),
            after=str(args.get("after") or ""),
            limit=int(args.get("limit") or 20),
        )
    if name == "dig_tenant_cm":
        from services.owner_copilot.tools_dig import tool_dig_tenant_cm

        return await tool_dig_tenant_cm(tenant_id=tenant_id, role=role, user_id=user_id)
    if name == "propose_channel_flags":
        from services.owner_copilot.tools_dig import tool_propose_channel_flags

        return await tool_propose_channel_flags(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            patch=dict(args.get("patch") or {}),
        )
    return None
