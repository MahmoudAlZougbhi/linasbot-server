"""Message-catalog intended prices. Live checkout MRR stays on the credit catalog."""

from __future__ import annotations

from typing import Any


def intended_price_usd(plan_id: str) -> float | None:
    pid = (plan_id or "").strip().lower()
    if not pid or pid in {"none", "free"}:
        return None
    try:
        from services.membership.catalog_admin import effective_offer_fields

        value = effective_offer_fields(pid).get("intended_price_usd")
    except Exception:
        return None
    if value in (None, ""):
        return None
    return float(value)


def intended_message_mrr(plan_ids: list[str]) -> float:
    total = 0.0
    for plan_id in plan_ids:
        price = intended_price_usd(plan_id)
        if price is not None:
            total += price
    return round(total, 2)


def live_checkout_mrr(plan_ids: list[str]) -> float:
    from services.plan_economics import PLAN_PRICES_USD

    total = 0.0
    for plan_id in plan_ids:
        total += float(PLAN_PRICES_USD.get((plan_id or "").strip().lower(), 0.0))
    return round(total, 2)


def revenue_pair(plan_ids: list[str]) -> dict[str, Any]:
    return {
        "live_checkout_mrr_usd": live_checkout_mrr(plan_ids),
        "intended_message_mrr_usd": intended_message_mrr(plan_ids),
        "note": "intended_message_mrr_usd is the message catalog. live_checkout_mrr_usd is membership-v1 until cutover.",
    }
