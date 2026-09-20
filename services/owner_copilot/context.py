"""Compact owner-chat context packing (no full CM dump / full history every turn)."""

from __future__ import annotations

from typing import Any

from services.owner_copilot.account_state import build_account_summary
from services.owner_copilot.onboarding import is_welcome_chip_prompt
from services.owner_copilot.profile import normalize_language, resolve_owner_reply_language
from services.owner_copilot.sol_app_knowledge import retrieve_sol_app_knowledge, sol_knowledge_prompt_block
from services.owner_copilot.sol_identity import compose_sol_system, load_sol_identity
from services.runtime_limits.loader import load_runtime_limits
from services.runtime_limits.window import window_owner_messages

SUMMARY_EVERY_N = 12


def _trim(text: str, limit: int = 120) -> str:
    """Summary-only trim for older turns. Packed owner messages are not clipped at 600."""
    t = (text or "").strip()
    if limit <= 0 or len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


def summarize_conversation(messages: list[dict[str, Any]], *, keep: int = 100) -> str | None:
    """Cheap extractive summary when history grows — not a full transcript."""
    if len(messages) < SUMMARY_EVERY_N:
        return None
    cap = max(1, int(keep))
    older = messages[:-cap] if len(messages) > cap else []
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
    Sol persona is published portal CM only (sol_system). Empty portal → sol_unconfigured.
    """
    limits = load_runtime_limits(tenant_id)
    msgs = list(messages or [])
    windowed = window_owner_messages(
        msgs,
        n=limits.owner_history_messages,
        max_chars=limits.owner_message_max_chars,
    )
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
    identity = load_sol_identity(tenant_id)
    configured = bool(identity.get("configured"))
    raw_payload = identity.get("payload")
    payload: dict[str, Any] = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    sol_system = compose_sol_system(payload) if configured else ""
    knowledge_items = retrieve_sol_app_knowledge(tenant_id, user_text) if configured else []
    recent = [{"role": m.get("role"), "content": str(m.get("content") or "")} for m in windowed]
    summary = summarize_conversation(msgs, keep=limits.owner_history_messages)
    return {
        "sol_system": sol_system,
        "sol_unconfigured": not configured,
        "owner_history_messages": limits.owner_history_messages,
        "owner_message_max_chars": limits.owner_message_max_chars,
        "account_summary": {
            "setup_stage": account.get("setup_stage"),
            "cm": account.get("cm"),
            "integrations": account.get("integrations"),
            "plan_id": (account.get("plan") or {}).get("plan_id") or (account.get("plan") or {}).get("plan"),
            "messages_brief": account.get("messages"),
            "profile": {
                "display_name": (account.get("profile") or {}).get("display_name"),
                "gender": (account.get("profile") or {}).get("gender"),
                "preferred_language": preferred,
                "form_of_address": (account.get("profile") or {}).get("form_of_address"),
            },
        },
        "knowledge_block": sol_knowledge_prompt_block(knowledge_items),
        "recent_messages": recent,
        "conversation_summary": summary,
        "reply_language": reply_lang,
        "preferred_language": preferred,
        "cm_full_dump": False,
        "full_history": False,
    }


def estimate_context_tokens(context: dict[str, Any]) -> int:
    """Rough token estimate for owner-chat usage tracking (~4 chars/token)."""
    import json

    blob = json.dumps(context, ensure_ascii=False, default=str)
    return max(1, len(blob) // 4)
