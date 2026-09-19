"""Public + tenant plan catalog APIs (single server-side SoT)."""

from __future__ import annotations

from typing import Any

from modules.core import app
from services.billing.membership.feature_entitlements import additional_seats_for_plan, channel_flags_for_plan
from services.billing.membership.message_catalog import offer_fields_for_plan
from services.billing.membership.plan_catalog import catalog_snapshot, public_plan_matrix, topup_pack_matrix


@app.get("/api/public/plans")
async def public_plans() -> Any:
    """Safe public catalog for marketing/pricing — no margin/cost internals."""
    plans = []
    for row in public_plan_matrix():
        offer = offer_fields_for_plan(row["plan_id"])
        flags = channel_flags_for_plan(row["plan_id"])
        known_seats, message_seats = additional_seats_for_plan(row["plan_id"])
        seats = message_seats if known_seats else row["additional_seats"]
        features = {
            k: v
            for k, v in row["features"].items()
            if k
            in {
                "owner_assistant",
                "content_management",
                "customer_dm_automation",
                "faq_enabled",
                "comment_automation",
                "whatsapp",
                "web",
                "tiktok",
                "tenant_analytics",
                "instagram_dm",
                "facebook_dm",
            }
        }
        features.update(flags)
        plans.append(
            {
                "plan_id": row["plan_id"],
                "display_name": row["display_name"],
                "price_usd": offer.get("intended_price_usd", row["price_usd"]),
                "intended_price_usd": offer.get("intended_price_usd", row["price_usd"]),
                "live_store_price_usd": row["price_usd"],
                "included_credits": row["included_credits"],
                "included_messages": offer.get("included_messages"),
                "faq_capacity": offer.get("faq_capacity", row["faq_capacity"]),
                "additional_seats": seats,
                "additional_seats_unlimited": seats is None,
                "comment_automation": flags.get("comment_automation", row["comment_automation"]),
                "whatsapp": flags.get("whatsapp", row["whatsapp"]),
                "web": flags.get("web", row.get("web")),
                "tiktok": flags.get("tiktok", row["tiktok"]),
                "faq_enabled": True,
                "followup_enabled": True,
                "checkout_ready": True,
                "features": features,
                "tagline_key": row["plan_id"],
            }
        )
    return {
        "success": True,
        "catalog_version": catalog_snapshot()["catalog_version"],
        "billing_period": "monthly",
        "consumption_unit": "messages",
        "topup_unit": "messages",
        "checkout_ready": True,
        "plans": plans,
        "topup_packs": [
            {
                "price_usd": p["price_usd"],
                "purchased_messages": p["purchased_credits"],
                "purchased_credits": p["purchased_credits"],
                "unit": "messages",
                "sale_ready": True,
                "expires": False,
            }
            for p in topup_pack_matrix()
        ],
        "credits_note": "Historical credit rows stay auditable.",
        "messages_note": "Subscription bills messages (plan allowance + extra message packs).",
    }
