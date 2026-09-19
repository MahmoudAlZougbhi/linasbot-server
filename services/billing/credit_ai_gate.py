"""Canonical remaining-message gate for Owner Copilot and channel AI.

Historical function names stay for import compatibility. The live meter is
the message ledger. Credit-ledger rows are not consulted for new turns.
"""

from __future__ import annotations

from typing import Any

from services.billing.membership.plan_catalog import is_highest_catalog_plan


def remaining_messages(tenant_id: str | None) -> int:
    tid = (tenant_id or "").strip().lower()
    if not tid:
        return 0
    try:
        from services.billing.membership.message_ledger import remaining_messages as ledger_remaining
        from services.billing.membership.period_grants import ensure_included_grant

        ensure_included_grant(tid)
        return max(0, int(ledger_remaining(tid)))
    except Exception:
        return 0


def remaining_credits(tenant_id: str | None) -> int:
    """Compatibility alias. Returns remaining message units."""
    return remaining_messages(tenant_id)


def _reserved_messages(tenant_id: str) -> int:
    try:
        from services.billing.membership.message_ledger import snapshot

        return max(0, int(snapshot(tenant_id).reserved))
    except Exception:
        return 0


def ai_generation_blocked(
    tenant_id: str | None,
    *,
    need: int = 1,
    honor_inflight_reserved: bool = False,
) -> bool:
    tid = (tenant_id or "").strip().lower()
    if not tid:
        return True
    if remaining_messages(tid) >= need:
        return False
    if honor_inflight_reserved and _reserved_messages(tid) >= need:
        return False
    return True


def upgrade_plan_allowed(plan_id: str | None) -> bool:
    return not is_highest_catalog_plan(plan_id)


def owner_credits_paused_payload(tenant_id: str | None, *, need: int = 1) -> dict[str, Any]:
    from services.billing.entitlements_service import entitlements_store

    tid = (tenant_id or "").strip().lower()
    remaining = remaining_messages(tid) if tid else 0
    required = max(1, int(need or 1))
    plan_id = entitlements_store.get(tid).plan_id if tid else "none"
    show_upgrade = upgrade_plan_allowed(plan_id)
    return {
        "code": "insufficient_messages",
        "message": (
            f"This action needs {required} messages. You have {remaining} remaining. "
            "Buy messages or upgrade to continue."
        ),
        "required": required,
        "remaining": remaining,
        "plan_id": plan_id,
        "show_upgrade": show_upgrade,
        "actions": {"buy_messages": True, "upgrade_plan": show_upgrade},
    }


def owner_credits_public(tenant_id: str | None) -> dict[str, Any]:
    tid = (tenant_id or "").strip().lower()
    if not tid:
        return {"unit": "messages", "remaining": 0, "available": False}
    return {"unit": "messages", "remaining": remaining_messages(tid), "available": True}
