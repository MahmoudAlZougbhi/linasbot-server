"""Subscription plan economics simulation (Wave 0).

Plan *prices* are fixed product requirements. Included usage allowances are
recommendations derived from configured provider rates — never invented to
match arbitrary x5/x10/x20 multiples without margin checks.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Final

from services.model_pricing import MODEL_PRICING

# Fixed list prices (USD / month) — do not change without Mahmoud approval.
PLAN_PRICES_USD: Final[dict[str, float]] = {
    "starter": 24.99,
    "growth": 59.0,
    "pro": 109.0,
    "max": 250.0,
}

# Feature entitlements (product requirements; independent of token allowances).
PLAN_FEATURES: Final[dict[str, dict[str, bool]]] = {
    "starter": {
        "owner_assistant": True,
        "content_management": True,
        "ai_setup": True,
        "customer_dm_automation": True,
        "basic_integrations": True,
        "faq_enabled": True,
        "comment_automation": False,
        "creative_studio": False,
        "scheduling": False,
        "image_generation": False,
        "video_generation": False,
    },
    "growth": {
        "owner_assistant": True,
        "content_management": True,
        "ai_setup": True,
        "customer_dm_automation": True,
        "basic_integrations": True,
        "faq_enabled": True,
        "comment_automation": True,
        "creative_studio": False,
        "scheduling": False,
        "image_generation": False,
        "video_generation": False,
    },
    "pro": {
        "owner_assistant": True,
        "content_management": True,
        "ai_setup": True,
        "customer_dm_automation": True,
        "basic_integrations": True,
        "faq_enabled": True,
        "comment_automation": True,
        "creative_studio": True,
        "scheduling": True,
        "image_generation": True,
        "video_generation": True,
    },
    "max": {
        "owner_assistant": True,
        "content_management": True,
        "ai_setup": True,
        "customer_dm_automation": True,
        "basic_integrations": True,
        "faq_enabled": True,
        "comment_automation": True,
        "creative_studio": True,
        "scheduling": True,
        "image_generation": True,
        "video_generation": True,
        "advanced_capabilities": True,
    },
}

# Smart Answers / FAQ entry caps — central plan config (not scattered constants).
# Policy: no paid plan → disabled; entry plans ~200; higher tiers ~1000.
PLAN_FAQ_MAX_ENTRIES: Final[dict[str, int]] = {
    "none": 0,
    "starter": 200,
    "growth": 200,
    "pro": 1000,
    "max": 1000,
}

# Assumed unit costs (USD) — image/video from typical production list prices; text from MODEL_PRICING.
DEFAULT_IMAGE_COST_USD: Final[float] = 0.04  # gpt-image / similar mid tier
DEFAULT_VIDEO_COST_USD: Final[float] = 0.50  # placeholder per short clip unit; provider-pluggable
APP_STORE_FEE_PCT: Final[float] = 0.15  # small-business rate assumption for modeling
INFRA_ALLOC_USD: Final[dict[str, float]] = {
    "starter": 2.0,
    "growth": 4.0,
    "pro": 8.0,
    "max": 15.0,
}

# Target gross margin floor after store fee + provider + infra (pathological 100% use).
TARGET_MARGIN_FLOOR: Final[float] = 0.25

# Customer DM model (high volume) vs owner chat model (balanced).
DM_MODEL: Final[str] = "gpt-4o-mini"
OWNER_MODEL: Final[str] = "gpt-5-mini"
SETUP_MODEL: Final[str] = "gpt-5-mini"

# Tokens per typical operation (estimates for allowance sizing).
TOKENS_PER_DM: Final[tuple[int, int]] = (800, 250)  # in, out
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
    pricing = MODEL_PRICING.get(model) or MODEL_PRICING["gpt-4o-mini"]
    return (input_tokens / 1_000_000) * float(pricing["input"]) + (output_tokens / 1_000_000) * float(pricing["output"])


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


def _max_affordable_provider_budget(plan_id: str) -> float:
    price = PLAN_PRICES_USD[plan_id]
    store = price * APP_STORE_FEE_PCT
    infra = INFRA_ALLOC_USD[plan_id]
    # Keep TARGET_MARGIN_FLOOR of list price as contribution after costs.
    return max(0.0, price - store - infra - (price * TARGET_MARGIN_FLOOR))


def recommend_allowance(plan_id: str) -> PlanAllowanceRecommendation:
    """Size included usage so 100% legitimate use stays above margin floor."""
    price = PLAN_PRICES_USD[plan_id]
    budget = _max_affordable_provider_budget(plan_id)
    features = PLAN_FEATURES[plan_id]

    # Seed mixes scaled by plan tier; shrink until budget fits.
    seeds: dict[str, dict[str, int]] = {
        "starter": {"dm": 800, "owner": 120, "setup": 40, "images": 0, "videos": 0},
        "growth": {"dm": 3500, "owner": 250, "setup": 60, "images": 0, "videos": 0},
        "pro": {"dm": 6000, "owner": 400, "setup": 80, "images": 40, "videos": 4},
        "max": {"dm": 12000, "owner": 800, "setup": 120, "images": 100, "videos": 12},
    }
    mix = dict(seeds[plan_id])
    if not features.get("comment_automation"):
        pass  # DM seed already includes comments=0 for starter
    if not features.get("image_generation"):
        mix["images"] = 0
    if not features.get("video_generation"):
        mix["videos"] = 0

    cost = _cost_for_mix(**mix)
    scale = 1.0
    if cost > budget > 0:
        scale = budget / cost
        for key in mix:
            mix[key] = int(mix[key] * scale)

    final_cost = _cost_for_mix(**mix)
    store = price * APP_STORE_FEE_PCT
    infra = INFRA_ALLOC_USD[plan_id]
    margin = (price - store - infra - final_cost) / price if price else 0.0

    # Internal credits: 1 credit ~= $0.001 provider cost (display abstraction).
    credits = max(1, int(round(final_cost * 1000)))

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
        margin_ok=margin >= TARGET_MARGIN_FLOOR - 0.001,
        notes=(
            f"Scaled by {scale:.3f} to fit margin floor {TARGET_MARGIN_FLOOR:.0%}."
            if scale < 0.999
            else "Seed mix fits margin floor without scaling."
        ),
    )


def usage_scenario(
    plan_id: str,
    allowance: PlanAllowanceRecommendation,
    pct: float,
) -> dict[str, Any]:
    """Estimate economics at a fraction of included allowance."""
    fraction = max(0.0, min(1.0, pct))
    provider = allowance.max_provider_cost_usd * fraction
    price = allowance.price_usd
    store = allowance.store_fee_usd
    infra = allowance.infra_usd
    # Infra is mostly fixed; store fee is on revenue.
    gross = price - store - infra - provider
    return {
        "usage_pct": pct,
        "subscription_revenue_usd": price,
        "provider_cost_usd": round(provider, 4),
        "store_fee_usd": store,
        "infra_allocation_usd": infra,
        "gross_profit_usd": round(gross, 4),
        "gross_margin": round(gross / price, 4) if price else 0.0,
    }


def build_economics_report() -> dict[str, Any]:
    """Machine-readable report for Wave 0 / Wave 4 acceptance."""
    pricing_date = datetime.now(UTC).date().isoformat()
    plans: list[dict[str, Any]] = []
    for plan_id in ("starter", "growth", "pro", "max"):
        allowance = recommend_allowance(plan_id)
        scenarios = [usage_scenario(plan_id, allowance, p) for p in (0.25, 0.50, 1.0)]
        heavy = usage_scenario(plan_id, allowance, 1.0)
        heavy["label"] = "heavy_100pct_allowance"
        plans.append(
            {
                "plan_id": plan_id,
                "features": PLAN_FEATURES[plan_id],
                "allowance": asdict(allowance),
                "scenarios": scenarios,
                "flag_negative_economics": not allowance.margin_ok,
            }
        )
    return {
        "report_version": "phase2-wave0-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "pricing_source": {
            "text_models": "services.model_pricing.MODEL_PRICING",
            "text_pricing_date": pricing_date,
            "dm_model": DM_MODEL,
            "owner_model": OWNER_MODEL,
            "setup_model": SETUP_MODEL,
            "image_cost_usd_per_unit": DEFAULT_IMAGE_COST_USD,
            "video_cost_usd_per_unit": DEFAULT_VIDEO_COST_USD,
            "app_store_fee_pct": APP_STORE_FEE_PCT,
            "target_margin_floor": TARGET_MARGIN_FLOOR,
            "notes": (
                "Text rates from configured MODEL_PRICING (aligned with OpenAI public list). "
                "Image/video unit costs are configurable defaults pending provider router binding. "
                "Plan list prices are fixed product requirements."
            ),
        },
        "plans": plans,
        "credit_pack_hint": {
            "unit": "linas_credit",
            "approx_provider_usd_per_credit": 0.001,
            "note": "Extra packs priced in Wave 4 from same cost basis + margin policy.",
        },
    }
