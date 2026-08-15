"""Canonical five-plan membership catalog (frozen product matrix).

Server-side source of truth. Clients must consume the public/owner APIs — never invent prices.
Historical Wave0 4-plan contracts remain grandfatherable as hidden versions; public sales use these five.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

from services.membership.units import MICRO_USD_PER_USD, credits_to_millicredits

PlanId = Literal["lite", "starter", "growth", "pro", "max"]
SeatLimit = int | None  # None = unlimited (explicit; never a magic large number)


@dataclass(frozen=True)
class PlanDefinition:
    plan_id: PlanId
    display_name: str
    price_micro_usd: int
    included_credits: int  # whole credits granted per paid period
    included_millicredits: int
    faq_capacity: int  # non-deleted Q&A pairs (storage capacity)
    additional_seats: SeatLimit  # owner does not count; None = unlimited
    comment_automation: bool
    whatsapp: bool
    tiktok: bool
    public_sale: bool
    catalog_version: str


CATALOG_VERSION: Final[str] = "membership-v1-2026-08"

# Price micro-USD: $9.99 → 9_990_000, $25 → 25_000_000, etc.
_PLAN_ROWS: Final[tuple[tuple[PlanId, str, int, int, int, SeatLimit, bool], ...]] = (
    ("lite", "Lite", 9_990_000, 7_000, 50, 0, False),
    ("starter", "Starter", 25_000_000, 17_500, 110, 2, True),
    ("growth", "Growth", 59_000_000, 41_300, 250, 5, True),
    ("pro", "Pro", 109_000_000, 76_300, 600, None, True),
    ("max", "Max", 259_000_000, 181_300, 1_500, None, True),
)


def _whatsapp_for(plan_id: PlanId) -> bool:
    """WhatsApp messages: Lite excluded; Starter and above included."""
    return plan_id != "lite"


def _tiktok_for(plan_id: PlanId) -> bool:
    """TikTok DMs + comments: Growth, Pro, and Max (channel ships behind this flag)."""
    return plan_id in {"growth", "pro", "max"}


def _build_catalog() -> dict[str, PlanDefinition]:
    out: dict[str, PlanDefinition] = {}
    for plan_id, name, price_micro, credits, faq, seats, comments in _PLAN_ROWS:
        out[plan_id] = PlanDefinition(
            plan_id=plan_id,
            display_name=name,
            price_micro_usd=price_micro,
            included_credits=credits,
            included_millicredits=credits_to_millicredits(credits),
            faq_capacity=faq,
            additional_seats=seats,
            comment_automation=comments,
            whatsapp=_whatsapp_for(plan_id),
            tiktok=_tiktok_for(plan_id),
            public_sale=True,
            catalog_version=CATALOG_VERSION,
        )
    return out


PLAN_CATALOG: Final[dict[str, PlanDefinition]] = _build_catalog()
PUBLIC_PLAN_IDS: Final[tuple[str, ...]] = tuple(PLAN_CATALOG.keys())
HIGHEST_PUBLIC_PLAN_ID: Final[PlanId] = PUBLIC_PLAN_IDS[-1]


def is_highest_catalog_plan(plan_id: str | None) -> bool:
    """True only for the top public catalog plan (Max). Do not treat founder ``linas`` as Max."""
    return (plan_id or "").strip().lower() == HIGHEST_PUBLIC_PLAN_ID


# Top-up packs (purchased credits; never expire): 500 credits / $1
TOPUP_PACKS_USD: Final[tuple[int, ...]] = (10, 25, 40, 50, 100, 250)


def plan_price_usd(plan_id: str) -> float:
    """Display helper only — financial truth uses price_micro_usd."""
    plan = require_plan(plan_id)
    return plan.price_micro_usd / float(MICRO_USD_PER_USD)


def require_plan(plan_id: str) -> PlanDefinition:
    pid = (plan_id or "").strip().lower()
    if pid not in PLAN_CATALOG:
        raise KeyError(f"Unknown plan_id: {plan_id}")
    return PLAN_CATALOG[pid]


def plan_features(plan_id: str) -> dict[str, bool]:
    plan = require_plan(plan_id)
    return {
        "owner_assistant": True,
        "content_management": True,
        "ai_setup": True,
        "customer_dm_automation": True,
        "basic_integrations": True,
        "faq_enabled": True,
        "comment_automation": plan.comment_automation,
        "whatsapp": plan.whatsapp,
        "tiktok": plan.tiktok,
        "tenant_analytics": True,
        "instagram_dm": True,
        "facebook_dm": True,
        # Creative / media remain higher-tier product gates (unchanged policy beyond comments/FAQ/seats)
        "creative_studio": plan_id in {"pro", "max"},
        "scheduling": plan_id in {"pro", "max"},
        "image_generation": plan_id in {"pro", "max"},
        "video_generation": plan_id in {"pro", "max"},
        "advanced_capabilities": plan_id == "max",
    }


def public_plan_matrix() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plan_id in PUBLIC_PLAN_IDS:
        p = PLAN_CATALOG[plan_id]
        rows.append(
            {
                "plan_id": p.plan_id,
                "display_name": p.display_name,
                "price_usd": plan_price_usd(p.plan_id),
                "price_micro_usd": p.price_micro_usd,
                "included_credits": p.included_credits,
                "faq_capacity": p.faq_capacity,
                "additional_seats": p.additional_seats,
                "additional_seats_unlimited": p.additional_seats is None,
                "comment_automation": p.comment_automation,
                "whatsapp": p.whatsapp,
                "tiktok": p.tiktok,
                "features": plan_features(p.plan_id),
                "catalog_version": p.catalog_version,
                "public_sale": p.public_sale,
            }
        )
    return rows


def topup_pack_matrix() -> list[dict[str, Any]]:
    from services.membership.units import topup_usd_to_purchased_millicredits

    packs = []
    for usd in TOPUP_PACKS_USD:
        mc = topup_usd_to_purchased_millicredits(usd)
        packs.append(
            {
                "price_usd": usd,
                "price_micro_usd": usd * MICRO_USD_PER_USD,
                "purchased_credits": usd * 500,
                "purchased_millicredits": mc,
                "expires": False,
            }
        )
    return packs


def catalog_snapshot() -> dict[str, Any]:
    return {
        "catalog_version": CATALOG_VERSION,
        "credit_unit": {
            "definition": "1 credit = $0.001 actual AI provider cost",
            "millicredits_per_credit": 1000,
            "micro_usd_per_credit": 1000,
            "margin_on_debit": False,
        },
        "plans": public_plan_matrix(),
        "topup_packs": topup_pack_matrix(),
        "notes": [
            "Tenant owner does not count toward additional_seats.",
            "FAQ capacity counts non-deleted Q&A pairs (draft/disabled still occupy capacity).",
            "Included credits expire at paid-period end; purchased credits persist.",
            "Plan prices do not guarantee 30% net profit after store commission/taxes/infra.",
        ],
    }


def plan_definition_dict(plan_id: str) -> dict[str, Any]:
    return asdict(require_plan(plan_id))
