"""Small helpers extracted from brain.py (line-limit + typing isolation)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from services.owner_copilot_v2.models import StreamEvent

SYSTEM_V2 = (
    "You are Linas AI System Copilot — one brain for the authenticated business owner. "
    "Customer scope: Instagram/Facebook DMs and comments only. Creative/posts/images/videos are cancelled. "
    "Use typed tools for account, CM, integrations, diagnosis, setup, and price-list extraction. "
    "Never claim a tool ran unless you received a tool result. Never invent connection status or successes. "
    "After tools return, write a natural final answer (not JSON). High-impact writes need confirmation. "
    "Draft vs Live stay distinct. Live Chat is read-only in V2. "
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
        "validate_cm": "Validating your setup…",
        "propose_cm_patch": "Preparing a change proposal…",
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
