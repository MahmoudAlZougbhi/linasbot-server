"""Canonical remaining-credit gate for Owner Copilot and channel AI.

Dashboard remaining and every AI generation gate must use ``remaining_credits``.
This is the credit ledger spend wallet — not the prepaid token wallet, and not
the Linas Laser founder exemption (``linas`` only).
"""

from __future__ import annotations

from typing import Any

from services.membership.plan_catalog import is_highest_catalog_plan


def remaining_credits(tenant_id: str | None) -> int:
    """Available ledger credits — same number Dashboard shows as remaining."""
    tid = (tenant_id or "").strip().lower()
    if not tid:
        return 0
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.ensure_period_grant(tid)
        return max(0, int(credit_ledger_service.get_balance(tid)))
    except Exception:
        return 0


def _reserved_credits(tenant_id: str) -> int:
    try:
        from services.credit_ledger_service import credit_ledger_service

        return max(0, int(credit_ledger_service.get_reserved(tenant_id)))
    except Exception:
        return 0


def ai_generation_blocked(tenant_id: str | None, *, need: int = 1) -> bool:
    """True when the next AI turn cannot be funded from the credit ledger.

    Callers that already reserved (WhatsApp Cloud, delayed Meta DM) may show
    remaining 0 with reserved >= need — that is not a block.
    Missing tenant, ledger errors, and true zero with nothing reserved fail closed.
    """
    tid = (tenant_id or "").strip().lower()
    if not tid:
        return True
    if remaining_credits(tid) >= need:
        return False
    return _reserved_credits(tid) < need


def upgrade_plan_allowed(plan_id: str | None) -> bool:
    """Upgrade CTA only when the tenant is not already on the highest catalog plan (Max)."""
    return not is_highest_catalog_plan(plan_id)


def owner_credits_paused_payload(tenant_id: str | None) -> dict[str, Any]:
    """Structured Copilot pause payload for in-chat Buy credits / Upgrade buttons."""
    from services.entitlements_service import entitlements_store

    tid = (tenant_id or "").strip().lower()
    remaining = remaining_credits(tid) if tid else 0
    plan_id = entitlements_store.get(tid).plan_id if tid else "none"
    show_upgrade = upgrade_plan_allowed(plan_id)
    return {
        "code": "insufficient_credits",
        "message": "Not enough credits. Owner Copilot is paused until you buy credits or upgrade.",
        "remaining": remaining,
        "plan_id": plan_id,
        "show_upgrade": show_upgrade,
        "actions": {"buy_credits": True, "upgrade_plan": show_upgrade},
    }
