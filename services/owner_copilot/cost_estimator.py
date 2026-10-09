"""Estimate a Copilot turn in tokens, then map that range to messages."""

from __future__ import annotations

from typing import Any

from services.billing.membership.copilot_pricing import messages_for_tokens, needs_approval
from services.billing.membership.pricing_store import active_policy

_HEAVY = ("audit", "review everything", "fix everything", "fix all", "bulk", "import")


def _tokens(text: str) -> int:
    return max(1, len(text or "") // 4)


def estimate_turn(
    *,
    user_text: str,
    history_text: str = "",
    tool_schema_text: str = "",
    attachment_text: str = "",
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active = policy or active_policy()
    prompt = _tokens(user_text) + _tokens(history_text) + _tokens(tool_schema_text) + _tokens(attachment_text)
    lowered = (user_text or "").casefold()
    heavy = any(phrase in lowered for phrase in _HEAVY)
    tools = 12 if heavy else 1
    margin = float(active.get("estimate_margin") or 0.2)
    tokens_low = prompt + (4000 if heavy else 200)
    tokens_high = int(tokens_low * (1 + margin)) + (8000 if heavy else 0)
    messages_low = messages_for_tokens(tokens_low, active)
    messages_high = messages_for_tokens(tokens_high, active)
    return {
        "tokens_low": tokens_low,
        "tokens_high": tokens_high,
        "messages_low": messages_low,
        "messages_high": messages_high,
        "expected_tools": tools,
        "needs_approval": needs_approval(messages_high, active),
        "policy_version": active.get("policy_version"),
    }
