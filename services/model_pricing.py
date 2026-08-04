"""Model token rates and cost helpers for interaction / analytics logging.

OpenAI chat completion responses expose token usage, not dollar amounts.
Costs are estimated as: tokens × configured per-1M rates (USD).
"""

from __future__ import annotations

from typing import Any

# Per 1M tokens (input, output) — keep aligned with OpenAI public pricing.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-5.1": {"input": 1.25, "output": 10.0},
    "gpt-5.4": {"input": 1.25, "output": 10.0},
    "gpt-5.4-mini": {"input": 0.25, "output": 2.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-4o": {"input": 2.50, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4-turbo": {"input": 10.0, "output": 30.0},
}

COST_BASIS_TOKEN_RATES = "openai_usage_tokens_x_configured_rates"


def compute_cost_from_usage(model: str, prompt_tokens: int, completion_tokens: int) -> dict[str, Any]:
    """Compute input/output/total USD from token counts and configured rates."""
    pricing = MODEL_PRICING.get(model) or MODEL_PRICING.get("gpt-5.1") or {"input": 1.25, "output": 10.0}
    pt = int(prompt_tokens or 0)
    ct = int(completion_tokens or 0)
    input_cost = (pt / 1_000_000) * float(pricing["input"])
    output_cost = (ct / 1_000_000) * float(pricing["output"])
    return {
        "input_cost_usd": round(input_cost, 6),
        "output_cost_usd": round(output_cost, 6),
        "cost_usd": round(input_cost + output_cost, 6),
        "cost_basis": COST_BASIS_TOKEN_RATES,
        "cost_status": "estimated",
    }
