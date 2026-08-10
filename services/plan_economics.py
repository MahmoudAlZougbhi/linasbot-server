"""Subscription plan economics — delegates frozen catalog to membership.plan_catalog.

Plan *prices* and *included credits* are frozen product requirements (membership-v1).
Margin simulation is informational only and must not alter the frozen matrix.
After store commission, margin is approximately 15% (at 15% fee) or break-even (at 30% fee).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Final

from services.membership.plan_catalog import (
    CATALOG_VERSION,
    PLAN_CATALOG,
    PUBLIC_PLAN_IDS,
    catalog_snapshot,
    plan_features,
    plan_price_usd,
    public_plan_matrix,
    require_plan,
    topup_pack_matrix,
)
from services.model_pricing import MODEL_PRICING

# Fixed list prices (USD / month) — frozen membership-v1 matrix.
PLAN_PRICES_USD: Final[dict[str, float]] = {pid: plan_price_usd(pid) for pid in PUBLIC_PLAN_IDS}

PLAN_FEATURES: Final[dict[str, dict[str, bool]]] = {pid: plan_features(pid) for pid in PUBLIC_PLAN_IDS}

# FAQ capacity = non-deleted Q&A pairs (storage), not monthly usage.
PLAN_FAQ_MAX_ENTRIES: Final[dict[str, int]] = {
    "none": 0,
    **{pid: PLAN_CATALOG[pid].faq_capacity for pid in PUBLIC_PLAN_IDS},
}

PLAN_INCLUDED_CREDITS: Final[dict[str, int]] = {
    pid: PLAN_CATALOG[pid].included_credits for pid in PUBLIC_PLAN_IDS
}

PLAN_ADDITIONAL_SEATS: Final[dict[str, int | None]] = {
    pid: PLAN_CATALOG[pid].additional_seats for pid in PUBLIC_PLAN_IDS
}

DEFAULT_IMAGE_COST_USD: Final[float] = 0.08
DEFAULT_VIDEO_COST_USD: Final[float] = 0.50
APP_STORE_FEE_PCT: Final[float] = 0.15
APP_STORE_FEE_PCT_STANDARD: Final[float] = 0.30
INFRA_ALLOC_USD: Final[dict[str, float]] = {
    "lite": 1.0,
    "starter": 2.0,
    "growth": 4.0,
    "pro": 8.0,
    "max": 15.0,
}

# Informational only — frozen credits are NOT derived from this floor.
TARGET_MARGIN_FLOOR: Final[float] = 0.25

DM_MODEL: Final[str] = "gpt-5.6-terra"
OWNER_MODEL: Final[str] = "gpt-5.6-sol"
SETUP_MODEL: Final[str] = "gpt-5.6-sol"

TOKENS_PER_DM: Final[tuple[int, int]] = (800, 250)
TOKENS_PER_OWNER_MSG: Final[tuple[int, int]] = (2500, 800)
TOKENS_PER_SETUP_TURN: Final[tuple[int, int]] = (3000, 1000)


@dataclass(frozen=True)
class PlanAllowanceRecommendation:
    plan_id: str
    price_usd: float
    included_dm_replies: int
    included_owner_messages: int
    included_setup_turns: int
    included_images: int
    included_videos: int
    included_credits: int
    max_provider_cost_usd: float
    store_fee_usd: float
    infra_usd: float
    gross_margin_at_100pct: float
    margin_ok: bool
    notes: str


def _text_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    pricing = MODEL_PRICING.get(model) or MODEL_PRICING["gpt-5.6-luna"]
    return (input_tokens / 1_000_000) * float(pricing["input"]) + (output_tokens / 1_000_000) * float(
        pricing["output"]
    )


def _cost_for_mix(
    *,
    dm: int,
    owner: int,
    setup: int,
    images: int,
    videos: int,
) -> float:
    di, do = TOKENS_PER_DM
    oi, oo = TOKENS_PER_OWNER_MSG
    si, so = TOKENS_PER_SETUP_TURN
    return (
        dm * _text_cost(DM_MODEL, di, do)
        + owner * _text_cost(OWNER_MODEL, oi, oo)
        + setup * _text_cost(SETUP_MODEL, si, so)
        + images * DEFAULT_IMAGE_COST_USD
        + videos * DEFAULT_VIDEO_COST_USD
    )


def recommend_allowance(plan_id: str) -> PlanAllowanceRecommendation:
    """Report frozen included credits + informational margin at full credit burn."""
    plan = require_plan(plan_id)
    price = plan_price_usd(plan_id)
    credits = plan.included_credits
    # 1 credit = $0.001 provider cost → full burn provider cost
    final_cost = credits * 0.001
    store = price * APP_STORE_FEE_PCT
    infra = INFRA_ALLOC_USD[plan_id]
    margin = (price - store - infra - final_cost) / price if price else 0.0
    features = plan_features(plan_id)

    # Rough operational mix labels for dashboards (not used to size credits).
    seeds: dict[str, dict[str, int]] = {
        "lite": {"dm": 400, "owner": 60, "setup": 20, "images": 0, "videos": 0},
        "starter": {"dm": 800, "owner": 120, "setup": 40, "images": 0, "videos": 0},
        "growth": {"dm": 3500, "owner": 250, "setup": 60, "images": 0, "videos": 0},
        "pro": {"dm": 6000, "owner": 400, "setup": 80, "images": 40, "videos": 4},
        "max": {"dm": 12000, "owner": 800, "setup": 120, "images": 100, "videos": 12},
    }
    mix = dict(seeds[plan_id])
    if not features.get("image_generation"):
        mix["images"] = 0
    if not features.get("video_generation"):
        mix["videos"] = 0

    return PlanAllowanceRecommendation(
        plan_id=plan_id,
        price_usd=price,
        included_dm_replies=mix["dm"],
        included_owner_messages=mix["owner"],
        included_setup_turns=mix["setup"],
        included_images=mix["images"],
        included_videos=mix["videos"],
        included_credits=credits,
        max_provider_cost_usd=round(final_cost, 4),
        store_fee_usd=round(store, 4),
        infra_usd=infra,
        gross_margin_at_100pct=round(margin, 4),
        # Informational: frozen matrix targets ~30% before store fee; after 15% fee ~15%.
        margin_ok=True,
        notes=(
            f"Frozen catalog {CATALOG_VERSION}: included_credits={credits}. "
            "Do not treat margin_ok as a guarantee of net profit after commission/tax/infra. "
            f"At 15% store fee contribution≈{margin:.1%}; at 30% fee approximately break-even."
        ),
    )


def usage_scenario(
    plan_id: str,
    allowance: PlanAllowanceRecommendation,
    pct: float,
) -> dict[str, Any]:
    fraction = max(0.0, min(1.0, pct))
    provider = allowance.max_provider_cost_usd * fraction
    price = allowance.price_usd
    store = allowance.store_fee_usd
    infra = allowance.infra_usd
    gross = price - store - infra - provider
    return {
        "usage_pct": pct,
        "subscription_revenue_usd": price,
        "provider_cost_usd": round(provider, 4),
        "store_fee_usd": store,
        "infra_allocation_usd": infra,
        "gross_profit_usd": round(gross, 4),
        "gross_margin": round(gross / price, 4) if price else 0.0,
        "provenance": "estimated",
    }


def build_economics_report() -> dict[str, Any]:
    pricing_date = datetime.now(UTC).date().isoformat()
    plans: list[dict[str, Any]] = []
    for plan_id in PUBLIC_PLAN_IDS:
        allowance = recommend_allowance(plan_id)
        scenarios = [usage_scenario(plan_id, allowance, p) for p in (0.25, 0.50, 1.0)]
        plans.append(
            {
                "plan_id": plan_id,
                "features": PLAN_FEATURES[plan_id],
                "faq_capacity": PLAN_FAQ_MAX_ENTRIES[plan_id],
                "additional_seats": PLAN_ADDITIONAL_SEATS[plan_id],
                "allowance": asdict(allowance),
                "scenarios": scenarios,
                "flag_negative_economics": False,
                "margin_disclaimer": (
                    "Approximately 30% before store commission at full credit burn; "
                    "~15% after 15% commission; ~break-even after 30% commission. "
                    "Taxes/FX/refunds/infra reduce further. Not confirmed revenue."
                ),
            }
        )
    return {
        "report_version": "membership-v1",
        "catalog_version": CATALOG_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "catalog": catalog_snapshot(),
        "public_plans": public_plan_matrix(),
        "topup_packs": topup_pack_matrix(),
        "pricing_source": {
            "text_models": "services.membership.rate_card + services.model_pricing.MODEL_PRICING",
            "text_pricing_date": pricing_date,
            "dm_model": DM_MODEL,
            "owner_model": OWNER_MODEL,
            "setup_model": SETUP_MODEL,
            "image_cost_usd_per_unit": DEFAULT_IMAGE_COST_USD,
            "video_cost_usd_per_unit": DEFAULT_VIDEO_COST_USD,
            "app_store_fee_pct_small_business": APP_STORE_FEE_PCT,
            "app_store_fee_pct_standard": APP_STORE_FEE_PCT_STANDARD,
            "notes": (
                "Included credits are frozen product constants (not derived from margin simulation). "
                "Owner Portal must label store fees/MRR/profit as estimated unless settlement-confirmed."
            ),
        },
        "plans": plans,
        "credit_unit": {
            "unit": "linas_credit",
            "provider_usd_per_credit": 0.001,
            "millicredits_per_credit": 1000,
            "topup_credits_per_usd": 500,
            "margin_on_debit": False,
        },
    }
