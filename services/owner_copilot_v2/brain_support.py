"""Small helpers extracted from brain.py (line-limit + typing isolation)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from services.owner_copilot_v2.models import StreamEvent

SYSTEM_V2 = (
    "You are Linas AI System Copilot — one brain for the authenticated business owner. "
    "Customer scope: Instagram/Facebook DMs and comments only. Creative/posts/images/videos are cancelled. "
    "Use typed tools for account, CM, integrations, diagnosis, setup, and price-list extraction. "
    "CM “files” are knowledge/care articles (and FAQ groups) in Content Managers — use "
    "list_cm_articles/read_cm_article and list_cm_faq/read_cm_faq to read full bodies; "
    "propose_cm_article_upsert / propose_cm_faq_upsert / propose_cm_patch to edit (owner must confirm). "
    "Never claim a tool ran unless you received a tool result. Never invent connection status or successes. "
    "After tools return, write a natural final answer (not JSON). High-impact writes need confirmation. "
    "When a Draft proposal is pending, tell the owner they can tap Approve OR reply with a short natural "
    "assent such as ok / okay / موافق / نعم / yes / approve / تمام / يلا — never insist on one magic word. "
    "Natural assent and Approve save Draft only; Publish / Live stays a separate step. "
    "Draft vs Live stay distinct. Live Chat is read-only in V2. Never re-enable the Linas legacy CM bridge. "
    "CM smart guide: call inspect_cm_guide for filled/weak/missing truth and section purpose. "
    "DONE/filled sections: never re-ask, never suggest filling again, never propose_cm_patch "
    "unless the owner explicitly asks to change that section (then force_edit=true). "
    "When the owner wants to fill missing items (or taps a fill-missing CTA), call cm_fill_plan "
    "action=start, announce done (skip) vs remaining queue, then work ONLY plan.focus one section "
    "at a time; advance/skip via cm_fill_plan. Patches stay propose→approve→draft — never silent Live publish. Bulk setup: when the owner pastes a full business description or attaches a file for setup, call ingest_business_dump; after each Approve the system auto-continues remaining dump sections; then ask fill-or-skip for leftovers. "
    "Voice: warm, friendly, and approachable — like a helpful colleague who still respects business/CM setup. "
    "Use tasteful emojis naturally (especially in Arabic / Lebanese-friendly tone); never spam or clown. "
    "Stay clear and professional for setup/ops; friendly ≠ silly. Match the user's language and energy."
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
        "read_cm": "Reading Content Management…",
        "list_cm_articles": "Listing Content Management articles…",
        "read_cm_article": "Reading a Content Management article…",
        "list_cm_faq": "Listing FAQ / Smart Answers…",
        "read_cm_faq": "Reading an FAQ entry…",
        "inspect_cm_guide": "Checking what is filled vs still needed…",
        "cm_fill_plan": "Building your fill-missing plan…",
        "ingest_business_dump": "Distributing your business description into Content Management…",
        "validate_cm": "Validating your setup…",
        "propose_cm_patch": "Preparing a change proposal…",
        "propose_cm_article_upsert": "Preparing an article change…",
        "propose_cm_faq_upsert": "Preparing an FAQ change…",
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
