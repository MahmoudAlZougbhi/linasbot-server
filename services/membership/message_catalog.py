"""Intended message-subscription catalog. Not the live IAP/credit checkout SoT.

Paid monthly USD and included-message rows match the 2026-09-10 owner matrix.
Free remains unpublishable until section-2 commercial values are supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal

from services.membership.units import MICRO_USD_PER_USD

PlanId = Literal["free", "lite", "starter", "growth", "pro", "max"]
SeatLimit = int | None

MESSAGE_CATALOG_VERSION: Final[str] = "messages-v1-2026-09-10-draft"
MESSAGE_POLICY_VERSION: Final[str] = "message-policy-v1"
AI_SETUP_DAILY_EDIT_DEFAULT: Final[int] = 30

UNCONFIGURED_FREE_FIELDS: Final[tuple[str, ...]] = (
    "free_ai_message_allowance",
    "free_message_renewal",
    "knowledge_line_budget",
    "services_products_line_budget",
    "content_line_definition",
    "message_topup_prices",
    "credit_to_message_conversion",
)

TOPUP_PACK_QUANTITIES: Final[tuple[int, ...]] = (100, 300, 500, 1_000, 5_000)


@dataclass(frozen=True)
class MessagePlan:
    plan_id: PlanId
    display_name: str
    price_micro_usd: int
    included_messages: int | None
    faq_capacity: int
    additional_seats: SeatLimit
    comment_automation: bool
    whatsapp: bool
    web: bool
    tiktok: bool
    faq_enabled: bool
    followup_enabled: bool
    public_sale: bool
    services_cap: int | None
    products_cap: int | None
    branches_cap: int | None
    ai_setup_daily_edit_limit: int


def _paid(
    plan_id: PlanId,
    name: str,
    usd: int,
    messages: int,
    faq: int,
    seats: SeatLimit,
    comments: bool,
    whatsapp: bool,
    web: bool,
    tiktok: bool,
) -> MessagePlan:
    return MessagePlan(
        plan_id=plan_id,
        display_name=name,
        price_micro_usd=usd * MICRO_USD_PER_USD,
        included_messages=messages,
        faq_capacity=faq,
        additional_seats=seats,
        comment_automation=comments,
        whatsapp=whatsapp,
        web=web,
        tiktok=tiktok,
        faq_enabled=True,
        followup_enabled=True,
        public_sale=True,
        services_cap=None,
        products_cap=None,
        branches_cap=None,
        ai_setup_daily_edit_limit=AI_SETUP_DAILY_EDIT_DEFAULT,
    )


FREE_PLAN = MessagePlan(
    plan_id="free",
    display_name="Free",
    price_micro_usd=0,
    included_messages=None,
    faq_capacity=0,
    additional_seats=0,
    comment_automation=False,
    whatsapp=False,
    web=False,
    tiktok=False,
    faq_enabled=False,
    followup_enabled=False,
    public_sale=False,
    services_cap=5,
    products_cap=5,
    branches_cap=1,
    ai_setup_daily_edit_limit=AI_SETUP_DAILY_EDIT_DEFAULT,
)

PAID_PLANS: Final[dict[str, MessagePlan]] = {
    "lite": _paid("lite", "Lite", 10, 550, 50, 0, False, False, False, False),
    "starter": _paid("starter", "Starter", 29, 1_200, 110, 2, True, True, True, False),
    "growth": _paid("growth", "Growth", 59, 3_000, 250, 5, True, True, True, True),
    "pro": _paid("pro", "Pro", 120, 10_000, 600, None, True, True, True, True),
    "max": _paid("max", "Max", 279, 25_000, 1_500, None, True, True, True, True),
}

MESSAGE_PLAN_ORDER: Final[tuple[PlanId, ...]] = ("free", "lite", "starter", "growth", "pro", "max")
PUBLIC_PAID_PLAN_IDS: Final[tuple[str, ...]] = ("lite", "starter", "growth", "pro", "max")


def require_message_plan(plan_id: str) -> MessagePlan:
    pid = (plan_id or "").strip().lower()
    if pid == "free":
        return FREE_PLAN
    if pid not in PAID_PLANS:
        raise KeyError(f"Unknown message plan_id: {plan_id}")
    return PAID_PLANS[pid]


def price_usd(plan: MessagePlan) -> float:
    return plan.price_micro_usd / float(MICRO_USD_PER_USD)


def free_publish_blocked() -> bool:
    return True


def offer_fields_for_plan(plan_id: str) -> dict[str, Any]:
    plan = require_message_plan(plan_id)
    return {
        "included_messages": plan.included_messages,
        "intended_price_usd": price_usd(plan),
        "intended_price_micro_usd": plan.price_micro_usd,
        "faq_capacity": plan.faq_capacity,
        "faq_enabled": plan.faq_enabled,
        "followup_enabled": plan.followup_enabled,
        "ai_setup_daily_edit_limit": plan.ai_setup_daily_edit_limit,
        "message_policy_version": MESSAGE_POLICY_VERSION,
    }


def public_message_plans() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plan_id in PUBLIC_PAID_PLAN_IDS:
        plan = PAID_PLANS[plan_id]
        rows.append(
            {
                "plan_id": plan.plan_id,
                "display_name": plan.display_name,
                "intended_price_usd": price_usd(plan),
                "intended_price_micro_usd": plan.price_micro_usd,
                "included_messages": plan.included_messages,
                "faq_capacity": plan.faq_capacity,
                "additional_seats": plan.additional_seats,
                "additional_seats_unlimited": plan.additional_seats is None,
                "comment_automation": plan.comment_automation,
                "whatsapp": plan.whatsapp,
                "web": plan.web,
                "tiktok": plan.tiktok,
                "faq_enabled": plan.faq_enabled,
                "followup_enabled": plan.followup_enabled,
                "public_sale": plan.public_sale,
                "checkout_ready": False,
                "catalog_version": MESSAGE_CATALOG_VERSION,
                "message_policy_version": MESSAGE_POLICY_VERSION,
            }
        )
    return rows


def draft_topup_packs() -> list[dict[str, Any]]:
    return [
        {
            "pack_id": f"messages_{qty}",
            "quantity": qty,
            "price_usd": None,
            "expires": False,
            "sale_ready": False,
            "reason": "message_topup_prices",
        }
        for qty in TOPUP_PACK_QUANTITIES
    ]


def message_catalog_snapshot() -> dict[str, Any]:
    return {
        "catalog_version": MESSAGE_CATALOG_VERSION,
        "message_policy_version": MESSAGE_POLICY_VERSION,
        "consumption_unit": "messages",
        "checkout_ready": False,
        "publication_status": "draft",
        "ai_setup_daily_edit_limit": AI_SETUP_DAILY_EDIT_DEFAULT,
        "plans": public_message_plans(),
        "free": {
            "plan_id": "free",
            "display_name": FREE_PLAN.display_name,
            "public_sale": False,
            "publishable": False,
            "included_messages": None,
            "faq_enabled": False,
            "followup_enabled": False,
            "services_cap": FREE_PLAN.services_cap,
            "products_cap": FREE_PLAN.products_cap,
            "branches_cap": FREE_PLAN.branches_cap,
            "unconfigured_fields": list(UNCONFIGURED_FREE_FIELDS),
        },
        "topup_packs": draft_topup_packs(),
        "notes": [
            "One Message is one accepted Customer AI reply or sent AI follow-up.",
            "Smart FAQ answers do not consume messages.",
            "Live IAP checkout still uses the credit catalog until MESSAGE_BILLING_CUTOVER.",
            "Free cannot be published while required owner values are missing.",
        ],
    }
