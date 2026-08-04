"""Prepaid token package catalog priced at OpenAI cost × 1.30 (30% profit).

Production chat uses:
  - gpt-5.1 for orchestration / tool routing
  - gpt-5.4-mini for final customer-facing replies

Prepaid packs are priced on the **gpt-5.1** schedule (higher of the two) so
tenants are not under-charged when orchestration dominates. Token counts are
billable units matching Interaction Logs ``tokens`` (prompt + completion).

Assumption documented in UI: typical chat mix ≈ 80% input / 20% output tokens.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from services.model_pricing import MODEL_PRICING, compute_cost_from_usage

# Higher production chat model — conservative prepaid cost basis.
PACKAGE_PRICING_MODEL = "gpt-5.1"
INPUT_SHARE = 0.80
OUTPUT_SHARE = 0.20
PROFIT_MULTIPLIER = 1.30  # 30% profit on OpenAI cost

# Six retail packs: token sizes chosen so sell prices land near clean USD
# (owner example ~$8 cost → ~$10 sell maps roughly to the 2.5M pack).
PACKAGE_TOKEN_COUNTS: tuple[int, ...] = (
    250_000,
    500_000,
    1_000_000,
    2_500_000,
    5_000_000,
    10_000_000,
)


@dataclass(frozen=True)
class TokenPackage:
    id: str
    tokens: int
    openai_cost_usd: float
    sell_price_usd: float
    margin_pct: float
    price_per_1k_usd: float
    model: str
    input_share: float
    output_share: float
    basis: str

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["label"] = f"{self.tokens:,} tokens"
        data["currency"] = "USD"
        return data


def _split_tokens(total: int) -> tuple[int, int]:
    prompt = int(round(total * INPUT_SHARE))
    completion = max(0, total - prompt)
    return prompt, completion


def openai_cost_for_tokens(total_tokens: int, model: str = PACKAGE_PRICING_MODEL) -> float:
    prompt, completion = _split_tokens(int(total_tokens))
    result = compute_cost_from_usage(model, prompt, completion)
    return float(result["cost_usd"])


def sell_price_for_tokens(total_tokens: int, model: str = PACKAGE_PRICING_MODEL) -> float:
    cost = openai_cost_for_tokens(total_tokens, model=model)
    # Round to cents for retail checkout.
    return round(cost * PROFIT_MULTIPLIER, 2)


def build_package(tokens: int, model: str = PACKAGE_PRICING_MODEL) -> TokenPackage:
    tokens_i = int(tokens)
    if tokens_i <= 0:
        raise ValueError("tokens must be positive")
    cost = openai_cost_for_tokens(tokens_i, model=model)
    sell = sell_price_for_tokens(tokens_i, model=model)
    margin = 0.0 if cost <= 0 else round(((sell - cost) / cost) * 100.0, 2)
    per_1k = round(sell / (tokens_i / 1000.0), 4) if tokens_i else 0.0
    return TokenPackage(
        id=f"pack_{tokens_i}",
        tokens=tokens_i,
        openai_cost_usd=round(cost, 6),
        sell_price_usd=sell,
        margin_pct=margin,
        price_per_1k_usd=per_1k,
        model=model,
        input_share=INPUT_SHARE,
        output_share=OUTPUT_SHARE,
        basis=(
            f"Estimated prepaid tokens at {model} rates "
            f"({int(INPUT_SHARE * 100)}% input / {int(OUTPUT_SHARE * 100)}% output) "
            f"× {PROFIT_MULTIPLIER:.2f} sell multiplier (~30% profit on OpenAI cost)."
        ),
    )


def list_token_packages(model: str = PACKAGE_PRICING_MODEL) -> list[TokenPackage]:
    # Ensure model rates exist (fallback handled inside compute_cost_from_usage).
    _ = MODEL_PRICING.get(model) or MODEL_PRICING.get("gpt-5.1")
    return [build_package(n, model=model) for n in PACKAGE_TOKEN_COUNTS]


def get_package(package_id: str, model: str = PACKAGE_PRICING_MODEL) -> TokenPackage | None:
    needle = (package_id or "").strip()
    for pack in list_token_packages(model=model):
        if pack.id == needle:
            return pack
    # Allow lookup by raw token count id variants.
    if needle.isdigit():
        tokens = int(needle)
        if tokens in PACKAGE_TOKEN_COUNTS:
            return build_package(tokens, model=model)
    return None


def catalog_public_payload() -> dict[str, Any]:
    packages = list_token_packages()
    return {
        "success": True,
        "pricing_model": PACKAGE_PRICING_MODEL,
        "profit_multiplier": PROFIT_MULTIPLIER,
        "input_share": INPUT_SHARE,
        "output_share": OUTPUT_SHARE,
        "basis": packages[0].basis if packages else "",
        "orchestration_model": "gpt-5.1",
        "final_response_model": "gpt-5.4-mini",
        "packages": [p.to_public_dict() for p in packages],
    }
