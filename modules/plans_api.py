"""Public + tenant plan catalog APIs (single server-side SoT)."""

from __future__ import annotations

from typing import Any

from modules.core import app
from services.membership.catalog_admin import effective_offer_fields
from services.membership.feature_entitlements import additional_seats_for_plan, channel_flags_for_plan
from services.membership.message_catalog import MESSAGE_CATALOG_VERSION
from services.membership.message_flags import message_billing_cutover
from services.membership.plan_catalog import catalog_snapshot, public_plan_matrix, topup_pack_matrix


@app.get("/api/public/plans")
async def public_plans() -> Any:
    """Safe public catalog for marketing/pricing — no margin/cost internals."""
    cutover = message_billing_cutover()
    plans = []
    for row in public_plan_matrix():
        offer = effective_offer_fields(row["plan_id"])
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
                "price_usd": offer["intended_price_usd"],
                "intended_price_usd": offer["intended_price_usd"],
                "live_store_price_usd": row["price_usd"],
                "included_credits": row["included_credits"],
                "included_messages": offer["included_messages"],
                "faq_capacity": offer["faq_capacity"],
                "additional_seats": seats,
                "additional_seats_unlimited": seats is None,
                "comment_automation": flags.get("comment_automation", row["comment_automation"]),
                "whatsapp": flags.get("whatsapp", row["whatsapp"]),
                "web": flags.get("web", row.get("web")),
                "tiktok": flags.get("tiktok", row["tiktok"]),
                "faq_enabled": offer["faq_enabled"],
                "followup_enabled": offer["followup_enabled"],
                "checkout_ready": cutover,
                "features": features,
                "tagline_key": row["plan_id"],
            }
        )
    return {
        "success": True,
        "catalog_version": catalog_snapshot()["catalog_version"],
        "message_catalog_version": MESSAGE_CATALOG_VERSION,
        "billing_period": "monthly",
        "consumption_unit": "messages",
        "topup_unit": "credits",
        "checkout_ready": cutover,
        "plans": plans,
        "topup_packs": [
            {
                "price_usd": p["price_usd"],
                "purchased_credits": p["purchased_credits"],
                "unit": "credits",
                "sale_ready": False,
                "expires": False,
            }
            for p in topup_pack_matrix()
        ]
        if not cutover
        else [],
        "messages_note": (
            "One AI message is one accepted customer reply or sent follow-up. "
            "Smart FAQ answers do not use your monthly messages. "
            "Included messages refresh each paid billing month."
        ),
        "credits_note": ("Historical credit purchases remain on file. New plans are measured in messages."),
    }
