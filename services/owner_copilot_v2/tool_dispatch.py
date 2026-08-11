"""Dispatch V2 tools with policy (creative blocked, shadow writes, Meta read-only)."""

from __future__ import annotations

import json
from typing import Any

from services.owner_ai_tools import HIGH_IMPACT_TOOLS, dispatch_tool
from services.owner_ai_tools_base import ToolResult
from services.owner_copilot_v2.creative_policy import CANCELLED_CREATIVE_TOOLS, creative_tool_blocked_result
from services.owner_copilot_v2.flags import (
    owner_copilot_meta_actions_enabled,
    owner_copilot_shadow_planning,
    owner_copilot_writes_enabled,
)

WRITE_TOOLS = frozenset(
    {
        "propose_cm_patch",
        "propose_cm_article_upsert",
        "propose_cm_faq_upsert",
        "propose_cm_delete",
        "approve_cm_patch",
        "publish_cm",
        "propose_diagnosis_fix",
        "approve_diagnosis_fix",
        "propose_smart_answer",
        "approve_smart_answer",
        "update_profile",
    }
)

META_MUTATION_TOOLS = frozenset(
    {
        "meta_disconnect",
        "meta_reconnect",
        "meta_reset_token",
        "meta_webhook_change",
    }
)


async def dispatch_v2_tool(
    name: str,
    *,
    tenant_id: str,
    user_id: str,
    role: str,
    args: dict[str, Any] | None = None,
    confirmed: bool = False,
    reply_language: str = "en",
) -> ToolResult:
    a = dict(args or {})

    if name in CANCELLED_CREATIVE_TOOLS or name in {"create_creative_draft", "schedule_creative_draft"}:
        blocked = creative_tool_blocked_result(name, language=reply_language)
        return ToolResult(
            ok=False,
            name=name,
            data=blocked.get("data") or {},
            error="creative_product_cancelled",
        )

    if name in META_MUTATION_TOOLS and not owner_copilot_meta_actions_enabled():
        return ToolResult(
            ok=False,
            name=name,
            data={"meta_mutations": False},
            error="meta_actions_disabled",
        )

    if name == "diagnose_meta_health":
        from services.owner_copilot_v2.diagnosis_health import tool_diagnose_meta_health

        return await tool_diagnose_meta_health(
            tenant_id=tenant_id,
            role=role,
            channel=str(a.get("channel") or "all"),
        )

    if name == "setup_next_step":
        from services.owner_copilot_v2.setup_flow import tool_setup_next_step

        return await tool_setup_next_step(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            action=str(a.get("action") or "status"),
            section=str(a["section"]) if a.get("section") else None,
        )

    if name == "extract_price_list":
        from services.owner_copilot_v2.vision_import import tool_extract_price_list

        return await tool_extract_price_list(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            attachment_id=str(a.get("attachment_id") or ""),
            notes=str(a.get("notes") or ""),
        )

    # Shadow / write kill switch: allow proposals to be created (they don't mutate live),
    # but block approve/publish/profile writes when writes disabled.
    mutating = name in {
        "approve_cm_patch",
        "publish_cm",
        "approve_diagnosis_fix",
        "approve_smart_answer",
        "update_profile",
    }
    if mutating and (not owner_copilot_writes_enabled() or owner_copilot_shadow_planning()):
        return ToolResult(
            ok=False,
            name=name,
            data={"shadow": True, "writes_enabled": False},
            error=(
                "AI Setup Draft writes are disabled on the server "
                "(OWNER_COPILOT_WRITES / shadow mode). Proposals can be reviewed, "
                "but Approve cannot save until writes are enabled."
            ),
        )

    # High-impact still requires confirmed flag from client
    if name in HIGH_IMPACT_TOOLS and name.startswith("approve_") and not confirmed:
        # Let underlying tool return requires_confirmation
        pass

    return await dispatch_tool(
        name,
        tenant_id=tenant_id,
        user_id=user_id,
        role=role,
        args=a,
        confirmed=confirmed,
    )


def tool_result_for_model(result: ToolResult) -> str:
    payload = {
        "ok": result.ok,
        "name": result.name,
        "data": result.data,
        "error": result.error,
        "requires_confirmation": result.requires_confirmation,
        "confirmation_token": result.confirmation_token,
    }
    # Article/FAQ reads are already chunked/bounded; allow a larger JSON envelope so
    # one full body chunk is not clipped mid-string by the default 8k cut.
    expanded = {
        "read_cm_article",
        "read_cm_faq",
        "list_cm_articles",
        "list_cm_faq",
        "read_cm",
    }
    limit = 24000 if result.name in expanded else 8000
    return json.dumps(payload, ensure_ascii=False, default=str)[:limit]
