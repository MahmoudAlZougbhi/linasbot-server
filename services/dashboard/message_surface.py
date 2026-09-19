"""Tenant-visible Subscription overlay. Live meter is message units."""

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
    snap = plan if isinstance(plan, dict) else {}
    remaining = snap.get("available_messages")
    included = int(snap.get("included_messages") or snap.get("granted_messages") or 0)
    return (None if remaining is None else int(remaining), included, True)


def overlay_message_fields(tenant_id: str, plan_id: str) -> dict[str, Any]:
    from services.billing.membership.catalog_admin import effective_included_messages
    from services.billing.membership.message_ledger import snapshot
    from services.billing.membership.period_grants import ensure_included_grant

    tid = (tenant_id or "").strip()
    intended = effective_included_messages(plan_id)
    if tid:
        ensure_included_grant(tid)
        snap = snapshot(tid)
        remaining = int(snap.remaining)
        included = int(snap.included)
        purchased = int(snap.purchased)
        reserved = int(snap.reserved)
        granted = included + purchased
        used = max(0, granted - remaining - reserved)
    else:
        remaining = included = purchased = reserved = granted = used = 0
    ratio = None
    if granted:
        ratio = min(1.0, max(0.0, used / float(granted)))
    return {
        "message_billing_active": True,
        "included_messages": intended,
        "purchased_messages": purchased,
        "reserved_messages": reserved,
        "available_messages": remaining,
        "included_remaining": included,
        "granted_messages": granted,
        "used_messages": used,
        "intended_included_messages": intended,
        "included_credits": _included_credits(plan_id),
        "usage_progress_ratio": ratio,
        "wallet_unit": "messages",
        "speak_as": "Wallet quantities are messages remaining.",
        "message_usage_note": "Subscription bills messages (plan allowance + extra message packs).",
    }


def copilot_usage_overlay(tenant_id: str, plan_id: str) -> dict[str, Any]:
    return overlay_message_fields(tenant_id, plan_id)
