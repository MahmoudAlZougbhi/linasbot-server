"""Small helpers extracted from brain.py (line-limit + typing isolation)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from services.owner_copilot.memory import pack_recent_messages
from services.owner_copilot.models import StreamEvent

FINAL_ANSWER_NUDGE = (
    "Write the natural final owner-facing answer now from the tool results. No JSON. "
    "If this was a CM review/check/problem/verify turn: (1) answer the specific ask, "
    "(2) include a proactive quality critique from quality_audit findings "
    "(duplicates, contradictions, unclear, suspicious, improvements/halwse) — "
    "not only the asked topic. Concise editor style; not a full CM dump. "
    "Offer propose→Approve→Live fixes when useful. "
    "Only paste full section/article bodies when the owner explicitly asked for them. "
    "Finish cleanly — never stop mid-sentence. "
    "Follow OUTPUT FORMAT: short intro + numbered/bulleted structure when listing; "
    "no dense walls of text; keep English product names intact."
)


def quick_actions(stage: str | None) -> list[dict[str, str]]:
    base = [
        {"id": "cm", "label": "Review Setup"},
        {"id": "usage", "label": "Check Usage"},
        {"id": "integrations", "label": "Integrations"},
    ]
    if stage in {"new", "cm_partial"}:
        return [{"id": "cm", "label": "Continue Setup"}, *base[1:]]
    return base


def status_label(name: str) -> str:
    return {
        "read_integrations": "Checking your Instagram/Facebook connection…",
        "diagnose_meta_health": "Reading Meta health evidence…",
        "read_cm": "Reading AI Setup…",
        "list_cm_articles": "Listing AI Setup articles…",
        "read_cm_article": "Reading an AI Setup article…",
        "list_cm_faq": "Listing FAQ / Smart Q&A…",
        "read_cm_faq": "Reading an FAQ entry…",
        "inspect_cm_guide": "Reviewing AI Setup quality…",
        "cm_fill_plan": "Building your fill-missing plan…",
        "ingest_business_dump": "Distributing your business description into AI Setup…",
        "validate_cm": "Validating your setup…",
        "propose_cm_patch": "Preparing a change proposal…",
        "propose_cm_article_upsert": "Preparing an article change…",
        "propose_cm_faq_upsert": "Preparing an FAQ change…",
        "propose_cm_delete": "Preparing delete confirmation…",
        "read_faq_quota": "Checking Smart Q&A / FAQ quota…",
        "propose_smart_answer": "Preparing a Smart Q&A for approval…",
        "approve_smart_answer": "Saving Smart Q&A and going Live…",
        "extract_price_list": "Reading the uploaded price list…",
        "setup_next_step": "Checking setup progress…",
        "get_recent_customer_interactions": "Loading recent customer interactions…",
        "get_interaction_trace": "Reading interaction TRACE…",
        "read_usage": "Checking usage…",
        "help": "Looking up product capabilities…",
        "list_pending_cm_proposals": "Listing pending proposals…",
        "approve_cm_batch": "Applying selected approvals…",
        "propose_comment_rule": "Preparing a comment/DM rule…",
        "list_connected_posts": "Loading connected posts…",
        "dig_tenant_cm": "Scanning AI Setup health…",
        "propose_channel_flags": "Preparing channel changes…",
    }.get(name, f"Running {name}…")


def done_payload(
    *,
    reply_text: str,
    tool_calls: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    choices: list[dict[str, Any]],
    model: str,
    ctx_tokens: int,
    stage: str,
    pending_confirmation: str | None = None,
    proposed_patch: dict[str, Any] | None = None,
    choice_set_id: str | None = None,
    reason: str = "sol_final",
    route: dict[str, Any] | None = None,
) -> dict[str, Any]:
    route_payload = route or {"kind": "owner_v2", "model": model, "reason": reason}
    if "kind" not in route_payload:
        route_payload = {"kind": "owner_v2", **route_payload}
    return {
        "reply_text": reply_text,
        "tool_calls": tool_calls,
        "cards": cards,
        "choices": choices,
        "choice_set_id": choice_set_id,
        "pending_confirmation": pending_confirmation,
        "proposed_patch": proposed_patch,
        "route": route_payload,
        "context_tokens": ctx_tokens,
        "setup_stage": stage,
        "quick_actions": quick_actions(stage),
        "model": model,
    }


async def emit_as_deltas(text: str, size: int = 28) -> AsyncIterator[StreamEvent]:
    for i in range(0, len(text or ""), size):
        yield StreamEvent(type="delta", payload={"text": text[i : i + size]})


def _build_messages(
    *,
    context: dict[str, Any],
    user_text: str,
    attachment_ids: list[str] | None = None,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    recent, summary = pack_recent_messages(
        context.get("recent_messages_raw") or context.get("recent_messages"),
        max_messages=int(context.get("owner_history_messages") or 100),
        max_chars=int(context.get("owner_message_max_chars") or 0),
    )
    persona = str(context.get("sol_system") or "").strip()
    parts = [
        persona,
        (
            f"Reply language (this turn): {context.get('reply_language') or 'en'}. "
            "Write the entire final answer in that language. "
            "It follows the owner's latest message language (not app Settings), "
            "except for welcome-chip/UI start prompts. "
            "Do not answer in English unless reply language is en."
        ),
        f"Account snapshot: {json.dumps(context.get('account_summary') or {}, ensure_ascii=False, default=str)[:2000]}",
    ]
    if context.get("knowledge_block"):
        parts.append(str(context["knowledge_block"]))
    if summary:
        parts.append(summary)
    if attachment_ids:
        parts.append(
            "User attached files are included in this user message "
            f"(ids={attachment_ids}). Read them. Use extract_price_list only for structured price-list import. "
            "For a full business dump (PDF/DOC/image/paste), call ingest_business_dump."
        )
    revise = context.get("proposal_revise")
    if isinstance(revise, dict) and revise:
        parts.append(
            "PROPOSAL EDIT MODE: The owner tapped Edit on a pending confirmation bar. "
            "Their next message revises THAT pending proposal — call the matching propose_* tool "
            "and return an updated bar. Pass replace_proposal_id="
            f"{revise.get('proposal_id')!s} when using propose_cm_delete. "
            "Do not ask for موافق. Do not start an unrelated new topic. "
            f"Pending proposal snapshot: {json.dumps(revise, ensure_ascii=False, default=str)[:4000]}"
        )
    out: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(p for p in parts if p)}]
    for m in recent:
        out.append({"role": m["role"], "content": m["content"]})
    user_content: str | list[dict[str, Any]] = user_text
    if attachment_ids and tenant_id:
        from services.owner_copilot.attachment_prompt import user_content_with_attachments

        user_content = user_content_with_attachments(
            tenant_id=tenant_id,
            user_text=user_text,
            attachment_ids=attachment_ids,
        )
    out.append({"role": "user", "content": user_content})
    return out
