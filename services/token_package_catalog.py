"""Prepaid AI packages with separate input + output token allotments.

Internal pricing (server-side only):
  cost_in  = input_tokens  / 1e6 * gpt-5.1 input rate
  cost_out = output_tokens / 1e6 * gpt-5.1 output rate
  sell     = round((cost_in + cost_out) * 1.30, 2)

Public API/UI never expose margin, cost basis, wholesale rates, or multipliers.
Each package card shows: price USD + input tokens included + output tokens included.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from services.model_pricing import MODEL_PRICING, compute_cost_from_usage

# Conservative prepaid basis: production orchestration model (higher of the pair).
PACKAGE_PRICING_MODEL = "gpt-5.1"
PROFIT_MULTIPLIER = 1.30  # internal only

# Six retail SKUs: (input_tokens, output_tokens). Equal allotments, clear round sizes.
# Sell prices are computed from model rates × 1.30 (not hand-picked odd blends).
PACKAGE_ALLOTMENTS: tuple[tuple[int, int], ...] = (
    (100_000, 100_000),
    (250_000, 250_000),
    (500_000, 500_000),
    (1_000_000, 1_000_000),
    (2_500_000, 2_500_000),
    (5_000_000, 5_000_000),
)

_PUBLIC_PACKAGE_FORBIDDEN_KEYS = frozenset(
    {
        "openai_cost_usd",
        "openai_input_cost_usd",
        "openai_output_cost_usd",
        "margin_pct",
        "model",
        "input_share",
        "output_share",
        "basis",
        "profit_multiplier",
        "pricing_model",
        "orchestration_model",
        "final_response_model",
        "cost_basis",
        "sell_multiplier",
    }
)


@dataclass(frozen=True)
class TokenPackage:
    id: str
    input_tokens: int
    output_tokens: int
    openai_input_cost_usd: float
    openai_output_cost_usd: float
    openai_cost_usd: float
    sell_price_usd: float
    margin_pct: float
    model: str
    basis: str

    @property
    def tokens(self) -> int:
        """Total prepaid units (input + output) — legacy alias for tests/checkout."""
        return int(self.input_tokens) + int(self.output_tokens)

    def to_public_dict(self) -> dict[str, Any]:
        """Customer-facing package card — price + input/output allowances only."""
        return {
            "id": self.id,
            "label": (
                f"{self.input_tokens:,} input + {self.output_tokens:,} output tokens"
            ),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "sell_price_usd": self.sell_price_usd,
            "currency": "USD",
            # Convenience totals for older UI paths (not a blended rate).
            "tokens": self.tokens,
        }

    def to_internal_dict(self) -> dict[str, Any]:
        data = self.to_public_dict()
        data.update(
            {
                "openai_input_cost_usd": self.openai_input_cost_usd,
                "openai_output_cost_usd": self.openai_output_cost_usd,
                "openai_cost_usd": self.openai_cost_usd,
                "margin_pct": self.margin_pct,
                "model": self.model,
                "basis": self.basis,
                "profit_multiplier": PROFIT_MULTIPLIER,
            }
        )
        return data


def openai_cost_for_allotment(
    input_tokens: int,
    output_tokens: int,
    model: str = PACKAGE_PRICING_MODEL,
) -> dict[str, float]:
    result = compute_cost_from_usage(model, int(input_tokens), int(output_tokens))
    return {
        "input_cost_usd": float(result["input_cost_usd"]),
        "output_cost_usd": float(result["output_cost_usd"]),
        "cost_usd": float(result["cost_usd"]),
    }


def sell_price_for_allotment(
    input_tokens: int,
    output_tokens: int,
    model: str = PACKAGE_PRICING_MODEL,
) -> float:
    costs = openai_cost_for_allotment(input_tokens, output_tokens, model=model)
    # Half-up to cents for clean retail prices (avoid banker's rounding surprises).
    raw = Decimal(str(costs["cost_usd"])) * Decimal(str(PROFIT_MULTIPLIER))
    return float(raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def build_package(
    input_tokens: int,
    output_tokens: int,
    model: str = PACKAGE_PRICING_MODEL,
) -> TokenPackage:
    inn = int(input_tokens)
    out = int(output_tokens)
    if inn <= 0 or out <= 0:
        raise ValueError("input_tokens and output_tokens must be positive")
    costs = openai_cost_for_allotment(inn, out, model=model)
    sell = sell_price_for_allotment(inn, out, model=model)
    cost = costs["cost_usd"]
    margin = 0.0 if cost <= 0 else round(((sell - cost) / cost) * 100.0, 2)
    return TokenPackage(
        id=f"pack_in{inn}_out{out}",
        input_tokens=inn,
        output_tokens=out,
        openai_input_cost_usd=round(costs["input_cost_usd"], 6),
        openai_output_cost_usd=round(costs["output_cost_usd"], 6),
        openai_cost_usd=round(cost, 6),
        sell_price_usd=sell,
        margin_pct=margin,
        model=model,
        basis=(
            f"Internal: {model} rates × {PROFIT_MULTIPLIER:.2f} on "
            f"({inn} input + {out} output). Not for public display."
        ),
    )


def list_token_packages(model: str = PACKAGE_PRICING_MODEL) -> list[TokenPackage]:
    _ = MODEL_PRICING.get(model) or MODEL_PRICING.get("gpt-5.1")
    return [build_package(inn, out, model=model) for inn, out in PACKAGE_ALLOTMENTS]


def get_package(package_id: str, model: str = PACKAGE_PRICING_MODEL) -> TokenPackage | None:
    needle = (package_id or "").strip()
    for pack in list_token_packages(model=model):
        if pack.id == needle:
            return pack
    # Legacy id lookup: pack_<total> no longer maps 1:1; reject unknown.
    return None


def catalog_public_payload() -> dict[str, Any]:
    packages = list_token_packages()
    return {
        "success": True,
        "summary": (
            "Prepaid AI token packs for company workspaces. Each pack includes a separate "
            "input-token allowance and output-token allowance. AI replies pause when either "
            "balance runs out until you recharge. FAQ-only answers that do not call the model "
            "may still work. Usage depends on how much knowledge and message context the AI reads "
            "and how you use messaging."
        ),
        "packages": [p.to_public_dict() for p in packages],
    }


def assert_public_payload_has_no_internal_economics(payload: dict[str, Any]) -> None:
    blob = str(payload).lower()
    forbidden_snippets = (
        "30% profit",
        "profit_multiplier",
        "sell multiplier",
        "openai cost",
        "cost_basis",
        "margin_pct",
        "openai_cost_usd",
        "gpt-5.1 rates",
        "1.30",
    )
    for snippet in forbidden_snippets:
        if snippet in blob:
            raise AssertionError(f"Public pricing leaked internal economics: {snippet!r}")
    for pack in payload.get("packages") or []:
        if not isinstance(pack, dict):
            continue
        leaked = _PUBLIC_PACKAGE_FORBIDDEN_KEYS.intersection(pack.keys())
        if leaked:
            raise AssertionError(f"Public package fields leaked: {sorted(leaked)}")
        if "input_tokens" not in pack or "output_tokens" not in pack:
            raise AssertionError("Public package must include input_tokens and output_tokens")
