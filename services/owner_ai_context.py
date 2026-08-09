"""Compact owner-chat context packing (no full CM dump / full history every turn)."""

from __future__ import annotations

from typing import Any

from services.owner_ai_account_state import build_account_summary
from services.system_knowledge_retrieval import (
    capabilities_as_prompt_block,
    detect_message_language,
    retrieve_capabilities,
)

SYSTEM_PROMPT = (
    "You are Linas AI System Copilot — the brain of the Linas AI app for business owners. "
    "Content Management setup is ONE capability, not the whole product. "
    "Be truthful about gated features (comments/publish live_verified, IAP purchase_ready). "
    "Never invent prices, routes, or successful actions. "
    "Never re-enable the Linas legacy CM bridge. "
    "High-impact actions (publish, post, schedule, delete, disconnect, spend) require confirmation. "
    "CM writes only via proposed patch → human preview → approval → validate → save. "
    "Reply in the language of the user's latest message when clear; otherwise use preferred_language. "
    "Never infer gender from email or name; use unset/neutral address if gender is unset."
)

MAX_RECENT_MESSAGES = 8
MAX_MESSAGE_CHARS = 600
SUMMARY_EVERY_N = 12


def _trim(text: str, limit: int = MAX_MESSAGE_CHARS) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def summarize_conversation(messages: list[dict[str, Any]]) -> str | None:
    """Cheap extractive summary when history grows — not a full transcript."""
    if len(messages) < SUMMARY_EVERY_N:
        return None
    older = messages[:-MAX_RECENT_MESSAGES]
    if not older:
        return None
    bits: list[str] = []
    for m in older[-10:]:
        role = str(m.get("role") or "?")
        content = _trim(str(m.get("content") or ""), 120)
        if content:
            bits.append(f"{role}: {content}")
    if not bits:
        return None
    return "Earlier conversation summary:\n" + "\n".join(bits)


def pack_owner_turn_context(
    *,
    tenant_id: str,
    user_id: str,
    user_text: str,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a small, structured context object for the orchestrator / future LLM turns."""
    msgs = list(messages or [])
    account = build_account_summary(tenant_id=tenant_id, user_id=user_id)
    preferred = str((account.get("profile") or {}).get("preferred_language") or "en")
    reply_lang = detect_message_language(user_text, fallback=preferred)
    caps = retrieve_capabilities(user_text, limit=4)
    recent = []
    for m in msgs[-MAX_RECENT_MESSAGES:]:
        recent.append(
            {
                "role": m.get("role"),
                "content": _trim(str(m.get("content") or "")),
            }
        )
    summary = summarize_conversation(msgs)
    knowledge_block = capabilities_as_prompt_block(caps)
    return {
        "system_prompt": SYSTEM_PROMPT,
        "account_summary": {
            "setup_stage": account.get("setup_stage"),
            "cm": account.get("cm"),
            "integrations": account.get("integrations"),
            "plan_id": (account.get("plan") or {}).get("plan_id") or (account.get("plan") or {}).get("plan"),
            "wallet_brief": account.get("wallet"),
            "profile": {
                "display_name": (account.get("profile") or {}).get("display_name"),
                "gender": (account.get("profile") or {}).get("gender"),
                "preferred_language": preferred,
                "form_of_address": (account.get("profile") or {}).get("form_of_address"),
            },
        },
        "knowledge_block": knowledge_block,
        "capabilities": [c.feature for c in caps],
        "recent_messages": recent,
        "conversation_summary": summary,
        "reply_language": reply_lang,
        "preferred_language": preferred,
        # Explicit: never attach full CM drafts here.
        "cm_full_dump": False,
        "full_history": False,
    }


def estimate_context_tokens(context: dict[str, Any]) -> int:
    """Rough token estimate for owner-chat usage tracking (~4 chars/token)."""
    import json

    blob = json.dumps(context, ensure_ascii=False, default=str)
    return max(1, len(blob) // 4)
