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
        from services.entitlements_service import entitlements_store

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
        "assumed_rate": None,
        "note": "Historical credits are preserved. 1 credit is not 1 message.",
    }
