"""Typed, authorized tools for the owner Linas AI System Copilot.

LLM / heuristic output never writes storage directly — tools call service APIs only.
CM writes go through propose → approve (human confirmation) then safe internal activation.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.owner_ai_tools_base import ToolResult
from services.owner_ai_tools_cm_bulk import tool_ingest_business_dump
from services.owner_ai_tools_cm_content import (
    tool_list_cm_articles,
    tool_list_cm_faq,
    tool_propose_cm_article_upsert,
    tool_propose_cm_faq_upsert,
    tool_read_cm_article,
    tool_read_cm_faq,
)
from services.owner_ai_tools_cm_guide import tool_cm_fill_plan, tool_inspect_cm_guide
from services.owner_ai_tools_creative import (
    tool_create_creative_draft,
    tool_schedule_creative_draft,
)
from services.owner_ai_tools_diagnosis import (
    tool_approve_diagnosis_fix,
    tool_get_interaction_trace,
    tool_get_recent_customer_interactions,
    tool_propose_diagnosis_fix,
)
from services.owner_ai_tools_faq import (
    tool_approve_smart_answer,
    tool_propose_smart_answer,
    tool_read_faq_quota,
)
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
    "inspect_cm_guide": tool_inspect_cm_guide,
    "cm_fill_plan": tool_cm_fill_plan,
    "ingest_business_dump": tool_ingest_business_dump,
    "list_cm_articles": tool_list_cm_articles,
    "read_cm_article": tool_read_cm_article,
    "list_cm_faq": tool_list_cm_faq,
    "read_cm_faq": tool_read_cm_faq,
    "validate_cm": tool_validate_cm,
    "propose_cm_patch": tool_propose_cm_patch,
    "propose_cm_article_upsert": tool_propose_cm_article_upsert,
    "propose_cm_faq_upsert": tool_propose_cm_faq_upsert,
    "approve_cm_patch": tool_approve_cm_patch,
    "publish_cm": tool_publish_cm,
    "read_usage": tool_read_usage,
    "read_subscription": tool_read_subscription,
    "read_integrations": tool_read_integrations,
    "read_dashboard_metrics": tool_read_dashboard_metrics,
    "read_scheduled_posts": tool_read_scheduled_posts,
    "read_jobs_errors": tool_read_jobs_errors,
    "update_profile": tool_update_profile,
    "get_recent_customer_interactions": tool_get_recent_customer_interactions,
    "get_interaction_trace": tool_get_interaction_trace,
    "propose_diagnosis_fix": tool_propose_diagnosis_fix,
    "approve_diagnosis_fix": tool_approve_diagnosis_fix,
    "read_faq_quota": tool_read_faq_quota,
    "propose_smart_answer": tool_propose_smart_answer,
    "approve_smart_answer": tool_approve_smart_answer,
    "create_creative_draft": tool_create_creative_draft,
    "schedule_creative_draft": tool_schedule_creative_draft,
}

HIGH_IMPACT_TOOLS: frozenset[str] = frozenset(
    {
        "publish_cm",
        "approve_cm_patch",
        "propose_cm_patch",
        "propose_cm_article_upsert",
        "propose_cm_faq_upsert",
        "propose_diagnosis_fix",
        "approve_diagnosis_fix",
        "propose_smart_answer",
        "approve_smart_answer",
        "ingest_business_dump",
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
    if name == "list_cm_articles":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            section=str(a.get("section") or "knowledge"),
            status=str(a["status"]) if a.get("status") else None,
            offset=int(a.get("offset") or 0),
            limit=int(a.get("limit") or 50),
        )
    if name == "read_cm_article":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            section=str(a.get("section") or ""),
            article_id=str(a.get("article_id") or a.get("id") or ""),
            body_offset=int(a.get("body_offset") or 0),
            body_limit=int(a.get("body_limit") or 6000),
        )
    if name == "list_cm_faq":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            status=str(a["status"]) if a.get("status") else None,
            offset=int(a.get("offset") or 0),
            limit=int(a.get("limit") or 50),
        )
    if name == "read_cm_faq":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            qa_group_id=str(a.get("qa_group_id") or ""),
        )
    if name == "inspect_cm_guide":
        include_guides = a.get("include_guides")
        return await handler(
            tenant_id=tenant_id,
            role=role,
            section=str(a["section"]) if a.get("section") else None,
            include_guides=True if include_guides is None else bool(include_guides),
        )
    if name == "cm_fill_plan":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            action=str(a.get("action") or "status"),
            section=str(a["section"]) if a.get("section") else None,
        )
    if name == "ingest_business_dump":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            text=str(a.get("text") or ""),
            reply_style=str(a.get("reply_style") or ""),
            attachment_id=str(a["attachment_id"]) if a.get("attachment_id") else None,
            propose_first=True if a.get("propose_first") is None else bool(a.get("propose_first")),
        )
    if name == "propose_cm_patch":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            section=str(a.get("section") or ""),
            patch=dict(a.get("patch") or {}),
            force_edit=bool(a.get("force_edit")),
        )
    if name == "propose_cm_article_upsert":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            section=str(a.get("section") or "knowledge"),
            article=dict(a.get("article") or {}),
        )
    if name == "propose_cm_faq_upsert":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            faq=dict(a.get("faq") or {}),
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
    if name == "get_recent_customer_interactions":
        return await handler(tenant_id=tenant_id, role=role, limit=int(a.get("limit") or 20))
    if name == "get_interaction_trace":
        return await handler(tenant_id=tenant_id, role=role, trace_id=str(a.get("trace_id") or ""))
    if name == "propose_diagnosis_fix":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            trace_id=str(a.get("trace_id") or ""),
            correction=dict(a.get("correction") or {}) or None,
        )
    if name == "approve_diagnosis_fix":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            proposal_id=str(a.get("proposal_id") or ""),
            confirmed=confirmed,
        )
    if name == "read_faq_quota":
        return await handler(tenant_id=tenant_id, role=role)
    if name == "propose_smart_answer":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            question=str(a.get("question") or ""),
            answer=str(a.get("answer") or ""),
            language=str(a.get("language") or "ar"),
        )
    if name == "approve_smart_answer":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            proposal_id=str(a.get("proposal_id") or ""),
            confirmed=confirmed,
        )
    if name == "create_creative_draft":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            prompt=str(a.get("prompt") or a.get("query") or ""),
            kind=str(a.get("kind") or a.get("creative_kind") or "") or None,
            compress=bool(a.get("compress")),
        )
    if name == "schedule_creative_draft":
        return await handler(
            tenant_id=tenant_id,
            role=role,
            user_id=user_id,
            text=str(a.get("text") or a.get("prompt") or ""),
            kind=str(a.get("kind") or "post"),
            platform=str(a.get("platform") or "") or None,
            scheduled_at=float(a["scheduled_at"]) if a.get("scheduled_at") is not None else None,
        )
    # Generic read tools
    return await handler(tenant_id=tenant_id, role=role)
