"""Public + tenant plan catalog APIs (single server-side SoT)."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from modules.core import app
from services.membership.plan_catalog import catalog_snapshot, public_plan_matrix, topup_pack_matrix


@app.get("/api/public/plans")
async def public_plans() -> Any:
    """Safe public catalog for marketing/pricing — no margin/cost internals."""
    plans = []
    for row in public_plan_matrix():
        plans.append(
            {
                "plan_id": row["plan_id"],
                "display_name": row["display_name"],
                "price_usd": row["price_usd"],
                "included_credits": row["included_credits"],
                "faq_capacity": row["faq_capacity"],
                "additional_seats": row["additional_seats"],
                "additional_seats_unlimited": row["additional_seats_unlimited"],
                "comment_automation": row["comment_automation"],
                "whatsapp": row["whatsapp"],
                "tiktok": row["tiktok"],
                "features": {
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
                        "tiktok",
                        "tenant_analytics",
                        "instagram_dm",
                        "facebook_dm",
                    }
                },
                "tagline_key": row["plan_id"],
            }
        )
    return {
        "success": True,
        "catalog_version": catalog_snapshot()["catalog_version"],
        "billing_period": "monthly",
        "plans": plans,
        "topup_packs": [
            {"price_usd": p["price_usd"], "purchased_credits": p["purchased_credits"], "expires": False}
            for p in topup_pack_matrix()
        ],
        # Customer-facing credit note only — never expose provider cost / margin.
        "credits_note": (
            "Included credits refresh at the start of each paid billing period and do not roll over. "
            "Credits purchased separately do not expire."
        ),
    }


@app.get("/api/billing/catalog")
async def billing_catalog(request: Request) -> Any:
    """Authenticated catalog mirror (same public fields; store mapping status separate)."""
    _ = request
    pub = await public_plans()
    return pub
