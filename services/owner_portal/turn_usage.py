"""Real provider token usage for one owner turn. Estimates stay flagged."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_USAGE: ContextVar[dict[str, int] | None] = ContextVar("owner_turn_usage", default=None)


def reset_provider_usage() -> None:
    _USAGE.set(None)


def add_provider_usage(prompt_tokens: Any, completion_tokens: Any) -> None:
    current = _USAGE.get()
    if current is None:
        current = {"prompt_tokens": 0, "completion_tokens": 0}
        _USAGE.set(current)
    current["prompt_tokens"] += int(prompt_tokens or 0)
    current["completion_tokens"] += int(completion_tokens or 0)


def consume_provider_usage() -> dict[str, int] | None:
    current = _USAGE.get()
    _USAGE.set(None)
    if not current or (current["prompt_tokens"] <= 0 and current["completion_tokens"] <= 0):
        return None
    return dict(current)


def priced_usage(
    *,
    qa_hit: bool,
    usage: dict[str, Any] | None,
    reply: str,
    message: str,
    model: str,
    given_in: int = 0,
    given_out: int = 0,
) -> dict[str, Any]:
    """Tokens and cost from provider usage, or a flagged length estimate."""
    if qa_hit:
        return {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "usage_estimated": False}
    prompt = int((usage or {}).get("prompt_tokens") or given_in or 0)
    completion = int((usage or {}).get("completion_tokens") or given_out or 0)
    estimated = prompt <= 0 and completion <= 0
    if estimated and (reply or message):
        completion = max(1, len(reply) // 4) if reply else 0
        prompt = max(1, len(message) // 4) if message else 0
    cost = 0.0
    if prompt or completion:
        from services.brain.model_pricing import compute_cost_from_usage

        cost = float(compute_cost_from_usage(model or "gpt-5.1", prompt, completion)["cost_usd"])
    return {
        "tokens_in": prompt,
        "tokens_out": completion,
        "cost_usd": cost,
        "usage_estimated": estimated,
    }
