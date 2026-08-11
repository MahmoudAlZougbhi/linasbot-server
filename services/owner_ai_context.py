"""Compact owner-chat context packing (no full CM dump / full history every turn)."""

from __future__ import annotations

from typing import Any

from services.owner_ai_account_state import build_account_summary
from services.owner_ai_onboarding import is_welcome_chip_prompt
from services.owner_ai_profile import normalize_language, resolve_owner_reply_language
from services.system_knowledge_retrieval import (
    capabilities_as_prompt_block,
    retrieve_capabilities,
)

SYSTEM_PROMPT = (
    "You are Linas AI System Copilot — the brain of the Linas AI app for business owners. "
    "Customer automation scope: Instagram/Facebook DMs and comments only. "
    "AI Setup is ONE capability, not the whole product. "
    "Creative Studio / Create Post / images / videos / scheduling are cancelled. "
    "Be truthful about gated features (comments live_verified, IAP purchase_ready). "
    "Never invent prices, routes, or successful actions. "
    "Never re-enable the Linas legacy CM bridge. "
    "High-impact actions (publish, delete, disconnect, spend) require confirmation. "
    "CM writes only via proposed patch → human preview → approval → validate → save → Live. "
    "Owner approval may be the Approve button OR a short natural assent "
    "(ok / okay / موافق / نعم / yes / approve / تمام / يلا) — never require one exact magic word. "
    "Assent and Approve apply the change Live for customer replies when activation succeeds; "
    "if activation fails, say so from the tool result and do not claim customers already see it. "
    "Live Chat is read-only for operators. "
    "Customer DM/comment reply language comes ONLY from AI Setup → Languages "
    "(system policy: supported languages + Franco→Arabic map + default). "
    "Neither the owner nor end customers can change customer reply language via Settings, "
    "profile preferred_language, or chat requests — refuse those and explain the CM rule. "
    "App Settings language is UI-only for the owner app chrome/welcome; it does not change DM/comment replies. "
    "Do not propose update_profile preferred_language to change how customers are answered. "
    "Reply in reply_language for this turn (detected from the owner's latest message; "
    "app locale only for welcome-chip/UI prompts or when detection is unclear). "
    "If the owner writes Arabic, answer in Arabic even when the app UI is English. "
    "If they write English or French, answer in that language. Franco/Arabizi → Arabic script. "
    "Never infer gender from email or name; use unset/neutral address if gender is unset. "
    "Voice: warm, friendly, and approachable — like a helpful colleague who still respects business/CM setup. "
    "Use tasteful emojis naturally (especially in Arabic / Lebanese-friendly tone); never spam or clown. "
    "Stay clear and professional for setup/ops; friendly ≠ silly. Match reply_language and energy."
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
    reply_language: str | None = None,
) -> dict[str, Any]:
    """Build a small, structured context object for the orchestrator / future LLM turns.

    Reply language follows the owner's latest message. App / preferred locale is only used
    for welcome-chip UI prompts (English tool text) and when detection is unclear.
    """
    msgs = list(messages or [])
    account = build_account_summary(tenant_id=tenant_id, user_id=user_id)
    preferred = normalize_language(
        (account.get("profile") or {}).get("preferred_language"),
        fallback="en",
    )
    reply_lang = resolve_owner_reply_language(
        user_text,
        reply_language_override=reply_language,
        preferred_language=preferred,
        treat_as_ui_prompt=is_welcome_chip_prompt(user_text),
    )
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
