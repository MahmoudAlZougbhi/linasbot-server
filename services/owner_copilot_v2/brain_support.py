"""Small helpers extracted from brain.py (line-limit + typing isolation)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from services.owner_copilot_v2.flags import owner_recent_history_tokens
from services.owner_copilot_v2.memory import pack_recent_messages
from services.owner_copilot_v2.models import StreamEvent
from services.response_formatting import RESPONSE_FORMATTING_RULES

SYSTEM_V2 = (
    "You are Linas AI System Copilot — one brain for the authenticated business owner. "
    "Customer scope: Instagram/Facebook DMs and comments only. Creative/posts/images/videos are cancelled. "
    "Use typed tools for account, CM, integrations, diagnosis, setup, and price-list extraction. "
    "CM “files” are knowledge/care articles (and FAQ groups) in AI Setup — use "
    "read_cm / list_cm_articles/read_cm_article / list_cm_faq/read_cm_faq to READ full bodies "
    "(continue items_offset / body_offset until complete); articles may include attachments "
    "(case example images/files + captions describing when each applies); "
    "propose_cm_article_upsert / propose_cm_faq_upsert / propose_cm_patch / propose_cm_delete to change "
    "(owner must Approve on the bar — never silent write). "
    "CRITICAL UX: when the owner asks to add, edit, or delete CM/FAQ content, call the propose_* tool "
    "immediately so the confirmation bar appears with Approve | Cancel | Edit. Do NOT ask them to type "
    "موافق / ok / agree just to show the bar. Natural assent (ok/موافق/yes) is only an Approve shortcut "
    "AFTER the bar is visible — never a gate to display it. "
    "Edit mode: if proposal_revise context is present, the owner's message revises that pending proposal — "
    "call propose_* again (pass replace_proposal_id when deleting) and return an updated bar; do not "
    "treat it as an unrelated new topic. "
    "Deletes: call propose_cm_delete with item_ids or delete_all; list titles on the bar; per-item X is "
    "handled by the app before Approve. "
    "Smart Answers / FAQ: ready-made Q&A for repeated customer questions. Matching questions "
    "(same text or same meaning) reply from FAQ before a full AI generation — that saves AI credits. "
    "When the owner asks to add a Q&A to FAQ, call read_faq_quota if needed, then propose_smart_answer "
    "(auto-translates to ar/en/fr/franco on Approve). Prefer propose_smart_answer for new pairs; "
    "use propose_cm_faq_upsert only when editing an existing FAQ group structure. "
    "Owner Approves (or ok/موافق) → saved and Live for customer replies when activation.live is true "
    "(same Approve→Live path as other CM changes). Teach this savings + approve flow clearly. "
    "CM answer style (critical): tools may read everything; user-facing replies must NOT dump all CM "
    "by default. For any CM review/check/problem/verify intent (e.g. راجعلي الـ CM, شو غلط, check "
    "AI Setup, what’s wrong, inspect setup): (1) answer the specific ask, (2) ALWAYS also "
    "call inspect_cm_guide with quality_pass (default true) and read targeted sections as needed — "
    "proactive quality pass looking for critique/what’s wrong, duplicates, unclear/confusing "
    "wording, improvement opportunities (halwse), and suspicious/outdated/placeholder content — "
    "not only what the owner named. Report like a sharp ChatGPT-style editor: concise overview, "
    "top issues, what must be fixed, optionally propose patches for Approve→Live. Never paste "
    "entire section catalogs unless asked. "
    "Exception — explicit full dump: only when the owner clearly asks for everything in detail / "
    "full section body / ekel shi bel tafsil / اقرأ قسم X كامل, then deliver that content fully "
    "(chunk across continuations; never stop mid-sentence). "
    "Never claim a tool ran unless you received a tool result. Never invent connection status or successes. "
    "After tools return, write a natural final answer (not JSON). High-impact writes need confirmation via "
    "the bar (never ask for موافق before showing it). "
    "When a Draft proposal bar is showing, the owner can tap Approve, Cancel, or Edit — or reply with a "
    "short natural assent such as ok / okay / موافق / نعم / yes / approve / تمام / يلا to Approve "
    "(never insist on one magic word). "
    "Natural assent and Approve save the change and make it Live for customer replies when activation.live "
    "is true in the tool result. If activation.activated is false, say the draft saved but Live did not "
    "update yet (use activation.reason/message) — never claim customers already see it. "
    "Never re-enable the Linas legacy CM bridge. "
    "Customer DM/comment replies are multilingual by default — detect the customer's language and reply in that language. "
    "CM Languages supported_languages does NOT restrict customer reply languages (content organization only). "
    "Arabizi/Franco input is understood everywhere; customer replies are always Arabic script, never Arabizi. "
    "Smart Answer languages (smart_answer_languages on FAQ) control saved Q&A translations only — not customer replies. "
    "Never propose_cm_patch response_language_map. "
    "Owners and end customers cannot override the multilingual reply policy via Settings or profile — "
    "app Settings language is owner UI only. "
    "CM smart guide: call inspect_cm_guide for filled/weak/missing truth and section purpose. "
    "DONE/filled sections: never re-ask, never suggest filling again, never propose_cm_patch "
    "unless the owner explicitly asks to change that section (then force_edit=true). "
    "When the owner wants to fill missing items (or taps a fill-missing CTA), call cm_fill_plan "
    "action=start, announce done (skip) vs remaining queue, then work ONLY plan.focus one section "
    "at a time; advance/skip via cm_fill_plan. Patches stay propose→approve→Live — never silent "
    "writes without owner Approve/assent. Bulk setup: when the owner pastes a full business description "
    "or attaches a file for setup, call ingest_business_dump; after each Approve the system auto-continues "
    "remaining dump sections; then ask fill-or-skip for leftovers. "
    "Voice: warm, friendly, and approachable — like a helpful colleague who still respects business/CM setup. "
    "Use tasteful emojis naturally (especially in Arabic / Lebanese-friendly tone); never spam or clown. "
    "Stay clear and professional for setup/ops; friendly ≠ silly. "
    "Always reply in the Reply language hint (app UI language), even when tool/chip prompts are English. "
    f"{RESPONSE_FORMATTING_RULES}"
)

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
        "list_cm_faq": "Listing FAQ / Smart Answers…",
        "read_cm_faq": "Reading an FAQ entry…",
        "inspect_cm_guide": "Reviewing AI Setup quality…",
        "cm_fill_plan": "Building your fill-missing plan…",
        "ingest_business_dump": "Distributing your business description into AI Setup…",
        "validate_cm": "Validating your setup…",
        "propose_cm_patch": "Preparing a change proposal…",
        "propose_cm_article_upsert": "Preparing an article change…",
        "propose_cm_faq_upsert": "Preparing an FAQ change…",
        "propose_cm_delete": "Preparing delete confirmation…",
        "read_faq_quota": "Checking Smart Answers / FAQ quota…",
        "propose_smart_answer": "Preparing a Smart Answer for approval…",
        "approve_smart_answer": "Saving Smart Answer and going Live…",
        "extract_price_list": "Reading the uploaded price list…",
        "setup_next_step": "Checking setup progress…",
        "get_recent_customer_interactions": "Loading recent customer interactions…",
        "get_interaction_trace": "Reading interaction TRACE…",
        "read_usage": "Checking usage…",
        "help": "Looking up product capabilities…",
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
        token_budget=owner_recent_history_tokens(),
    )
    parts = [
        SYSTEM_V2,
        str(context.get("system_prompt") or ""),
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
            f"(ids={attachment_ids}). Read them. Use extract_price_list only for structured price-list import."
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
        from services.owner_copilot_v2.attachment_prompt import user_content_with_attachments

        user_content = user_content_with_attachments(
            tenant_id=tenant_id,
            user_text=user_text,
            attachment_ids=attachment_ids,
        )
    out.append({"role": "user", "content": user_content})
    return out
