"""Inventory old credit balances. Never convert them into messages."""

from __future__ import annotations

from typing import Any


def conversion_blocked_reason() -> str:
    return "credit_to_message_conversion"


def _requested_ids(tenant_ids: list[str] | None) -> list[str]:
    return [tid.strip() for tid in (tenant_ids or []) if tid and tid.strip()]


def dry_run_credit_inventory(tenant_ids: list[str] | None = None) -> dict[str, Any]:
    """Read-only inventory. Does not mutate balances or invent a conversion rate."""
    rows: list[dict[str, Any]] = []
    try:
        from services.billing.entitlements_service import entitlements_store

        ids = _requested_ids(tenant_ids) or entitlements_store.list_tenant_ids()
        for tid in ids:
            ent = entitlements_store.get(tid)
            rows.append(
                {
                    "tenant_id": tid,
                    "plan_id": getattr(ent, "plan_id", None),
                    "status": getattr(ent, "status", None),
                    "included_credits": int(getattr(ent, "included_credits", 0) or 0),
                    "extra_credits": int(getattr(ent, "extra_credits", 0) or 0),
                    "converted": False,
                    "proposed_messages": None,
                }
            )
    except Exception as exc:
        return {
            "blocked": True,
            "reason": conversion_blocked_reason(),
            "error": type(exc).__name__,
            "tenants": [],
            "note": "Live conversion stays blocked until the owner approves a policy.",
        }
    return {
        "blocked": True,
        "reason": conversion_blocked_reason(),
        "tenant_count": len(rows),
        "tenants": rows,
        "assumed_rate": _configured_rate(),
        "note": "Historical credits are preserved. 1 credit is not 1 message.",
    }


def _configured_rate() -> float | None:
    try:
        from services.billing.membership.economy_policy import load_economy

        raw = load_economy().get("conversion_rate")
        return None if raw is None else float(raw)
    except Exception:
        return None


def apply_credit_conversion(*, tenant_ids: list[str] | None = None, dry_run: bool = True) -> dict[str, Any]:
    """Convert leftover credit balances only when Platform Owner set conversion_rate.

    Idempotent lot id: ``{tenant}:credit-conversion:{policy_version}``.
    Never guesses a rate. Historical credit rows stay.
    """
    inventory = dry_run_credit_inventory(tenant_ids)
    rate = _configured_rate()
    inventory["assumed_rate"] = rate
    if rate is None or rate <= 0:
        inventory["applied"] = False
        inventory["blocked"] = True
        inventory["note"] = "Conversion blocked until conversion_rate is configured."
        return inventory
    from services.billing.credit_ledger_service import credit_ledger_service
    from services.billing.membership.economy_policy import POLICY_VERSION, load_economy
    from services.billing.membership.message_ledger import grant_purchased, snapshot

    policy = str(load_economy().get("policy_version") or POLICY_VERSION)
    converted: list[dict[str, Any]] = []
    for row in inventory.get("tenants") or []:
        tid = str(row.get("tenant_id") or "")
        if not tid:
            continue
        lot_id = f"{tid}:credit-conversion:{policy}"
        existing = next((lot for lot in snapshot(tid).lots if lot.lot_id == lot_id), None)
        if existing is not None:
            converted.append({**row, "converted": True, "messages": existing.granted, "duplicate": True})
            continue
        remaining = int(credit_ledger_service.get_balance(tid) or 0)
        messages = int(remaining * rate)
        if messages <= 0:
            converted.append({**row, "converted": False, "messages": 0, "skipped": "zero_balance"})
            continue
        if dry_run:
            converted.append({**row, "converted": False, "proposed_messages": messages, "old_credits": remaining})
            continue
        lot = grant_purchased(
            tenant_id=tid,
            lot_id=lot_id,
            amount=messages,
            source_transaction_id=f"credit-conversion:{policy}:{tid}",
        )
        converted.append(
            {
                **row,
                "converted": True,
                "old_credits": remaining,
                "messages": messages,
                "lot_id": lot.lot_id,
                "policy_version": policy,
            }
        )
    inventory["blocked"] = dry_run
    inventory["applied"] = not dry_run
    inventory["tenants"] = converted
    inventory["tenant_count"] = len(converted)
    return inventory
