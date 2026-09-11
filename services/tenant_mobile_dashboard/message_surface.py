"""Tenant-visible message fields. Never expose credit quantities as messages."""

from __future__ import annotations

from typing import Any

from services.membership.catalog_admin import effective_offer_fields
from services.membership.message_flags import message_billing_enabled
from services.membership.message_ledger import snapshot_dict


def _live_lot_totals(snap: dict[str, Any]) -> tuple[int, int]:
    granted = 0
    remaining = 0
    for lot in snap.get("lots") or []:
        if not lot.get("live"):
            continue
        granted += int(lot.get("granted") or 0)
        remaining += int(lot.get("remaining") or 0)
    return granted, remaining


def _usage_progress_ratio(snap: dict[str, Any]) -> float | None:
    granted, remaining = _live_lot_totals(snap)
    if granted <= 0:
        return None
    used = max(0, granted - remaining)
    return min(1.0, used / float(granted))


def workspace_message_balance(plan: dict[str, Any]) -> tuple[int | None, int, bool]:
    """Quantities for tenant status/alerts. Never treat credit remaining as messages."""
    if not message_billing_enabled():
        return None, 0, False
    if plan.get("availability") != "ok":
        return None, 0, False
    remaining = plan.get("available_messages")
    included = int(plan.get("intended_included_messages") or plan.get("included_messages") or 0)
    if remaining is None:
        return None, included, False
    return int(remaining), included, True


def _wallet_honesty() -> dict[str, Any]:
    return {
        "wallet_unit": "credits",
        "speak_as": (
            "Wallet quantities are leftover credits, not Messages remaining. "
            "Use included_messages as the catalog allowance. Use available_messages "
            "only when message_billing_active is true; otherwise remaining is not active yet."
        ),
    }


def overlay_message_fields(tenant_id: str, plan_id: str) -> dict[str, Any]:
    try:
        intended = effective_offer_fields(plan_id).get("included_messages")
    except Exception:
        intended = None
    if not message_billing_enabled():
        return {
            "message_billing_active": False,
            "included_messages": intended,
            "purchased_messages": None,
            "reserved_messages": None,
            "available_messages": None,
            "included_remaining": None,
            "granted_messages": None,
            "used_messages": None,
            "intended_included_messages": intended,
            "usage_progress_ratio": None,
            "message_usage_note": (
                "Included messages are the catalog allowance. Live remaining is hidden until "
                "message billing is enabled. Historical credits stay on file and are not messages."
            ),
            **_wallet_honesty(),
        }
    from services.membership.period_grants import ensure_included_grant

    ensure_included_grant(tenant_id)
    snap = snapshot_dict(tenant_id)
    granted, remaining = _live_lot_totals(snap)
    return {
        "message_billing_active": True,
        "included_messages": intended,
        "purchased_messages": snap.get("purchased"),
        "reserved_messages": snap.get("reserved"),
        "available_messages": snap.get("remaining"),
        "included_remaining": snap.get("included"),
        "granted_messages": granted,
        "used_messages": max(0, granted - remaining),
        "intended_included_messages": intended,
        "usage_progress_ratio": _usage_progress_ratio(snap),
        "message_usage_note": "Remaining messages come from the message ledger, not the credit wallet.",
        **_wallet_honesty(),
    }


def copilot_usage_overlay(tenant_id: str, plan_id: str) -> dict[str, Any]:
    """Owner Copilot view. Leftover credits stay labeled credits."""
    return overlay_message_fields(tenant_id, plan_id)
