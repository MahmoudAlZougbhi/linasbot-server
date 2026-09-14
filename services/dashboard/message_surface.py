"""Tenant-visible Subscription overlay. Live meter is credits only."""

from __future__ import annotations

from typing import Any

from services.billing.membership.plan_catalog import PLAN_CATALOG


def _included_credits(plan_id: str) -> int | None:
    pid = (plan_id or "").strip().lower()
    plan = PLAN_CATALOG.get(pid)
    if plan is None:
        return None
    return int(plan.included_credits)


def workspace_message_balance(plan: dict[str, Any]) -> tuple[int | None, int, bool]:
    """Message remaining is not a live meter. Credits are the Subscription unit."""
    _ = plan
    return None, 0, False


def _wallet_honesty() -> dict[str, Any]:
    return {
        "wallet_unit": "credits",
        "speak_as": (
            "Wallet quantities are leftover credits, not Messages remaining. "
            "Use included_credits as the catalog allowance. Message remaining is not billed."
        ),
    }


def overlay_message_fields(tenant_id: str, plan_id: str) -> dict[str, Any]:
    """Fields for entitlements/me and /api/mobile/usage (mobile Subscription SoT)."""

    _ = tenant_id
    intended_credits = _included_credits(plan_id)
    return {
        "message_billing_active": False,
        "included_messages": None,
        "purchased_messages": None,
        "reserved_messages": None,
        "available_messages": None,
        "included_remaining": None,
        "granted_messages": None,
        "used_messages": None,
        "intended_included_messages": None,
        "included_credits": intended_credits,
        "usage_progress_ratio": None,
        "message_usage_note": (
            "Subscription bills credits (plan allowance + IAP credit packs). Message ledger remaining is not live."
        ),
        **_wallet_honesty(),
    }


def copilot_usage_overlay(tenant_id: str, plan_id: str) -> dict[str, Any]:
    """Owner Copilot view. Credits stay labeled credits."""
    return overlay_message_fields(tenant_id, plan_id)
