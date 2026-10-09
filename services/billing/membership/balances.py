"""Plan messages expire with the membership. Purchased messages do not."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def membership_can_grant(ent: Any, *, now: datetime | None = None) -> bool:
    status = str(getattr(ent, "status", "") or "").strip().lower()
    if status not in {"active", "trial", "grace"}:
        return False
    moment = now or datetime.now(UTC)
    end = getattr(ent, "current_period_end", None)
    if end is None:
        return True
    if isinstance(end, str):
        end = datetime.fromisoformat(end)
    if status == "grace":
        grace_end = getattr(ent, "grace_end", None)
        if isinstance(grace_end, str):
            grace_end = datetime.fromisoformat(grace_end)
        if grace_end is not None and moment < grace_end:
            return True
    return moment < end


def lot_expires_at(lot: Any) -> datetime | None:
    raw = getattr(lot, "expires_at", None)
    if raw is None:
        return None
    if isinstance(raw, str):
        return datetime.fromisoformat(raw)
    if isinstance(raw, datetime):
        return raw
    return None


def lot_is_live_now(lot: Any, *, now: datetime | None = None) -> bool:
    if not getattr(lot, "expires", True):
        return True
    expires_at = lot_expires_at(lot)
    if expires_at is None:
        from services.billing.membership.lot_window import current_period_id

        return str(getattr(lot, "period_id", "") or "") == current_period_id()
    moment = now or datetime.now(UTC)
    return moment < expires_at


def split_charge(*, plan_remaining: int, purchased_remaining: int, amount: int) -> tuple[int, int]:
    need = max(0, int(amount))
    from_plan = min(max(0, plan_remaining), need)
    from_purchased = min(max(0, purchased_remaining), need - from_plan)
    return from_plan, from_purchased


def tenant_balances(lots: list[Any], *, reserved: int = 0) -> dict[str, Any]:
    plan = [lot for lot in lots if getattr(lot, "kind", "") == "included"]
    purchased = [lot for lot in lots if getattr(lot, "kind", "") != "included"]
    plan_granted = sum(int(getattr(lot, "granted", 0)) for lot in plan)
    plan_remaining = sum(int(getattr(lot, "remaining", 0)) for lot in plan if lot_is_live_now(lot))
    purchased_granted = sum(int(getattr(lot, "granted", 0)) for lot in purchased)
    purchased_remaining = sum(int(getattr(lot, "remaining", 0)) for lot in purchased if lot_is_live_now(lot))
    plan_used = max(0, plan_granted - plan_remaining)
    purchased_used = max(0, purchased_granted - purchased_remaining)
    return {
        "plan": {
            "granted": plan_granted,
            "used": plan_used,
            "reserved": int(reserved),
            "remaining": plan_remaining,
            "status": "active" if plan_remaining else "expired",
        },
        "purchased": {
            "granted": purchased_granted,
            "used": purchased_used,
            "remaining": purchased_remaining,
            "never_expires": True,
        },
        "total_remaining": max(0, plan_remaining + purchased_remaining - int(reserved)),
        "used_messages": plan_used + purchased_used,
    }


def purchased_remaining(tenant_id: str) -> int:
    from services.billing.membership.message_ledger import snapshot

    return int(snapshot(tenant_id).purchased)


def subscription_blocks_replies(ent: Any, tenant_id: str) -> bool:
    status = str(getattr(ent, "status", "") or "").strip().lower()
    plan_id = str(getattr(ent, "plan_id", "") or "").strip().lower()
    inactive = status not in {"active", "trial", "grace"} or plan_id in {"", "none"}
    if not inactive:
        return False
    from services.platform.feature_flags import flag_enabled

    if not flag_enabled("period_balances"):
        return True
    from services.billing.membership.message_ledger import snapshot

    return int(snapshot(tenant_id).purchased) <= 0
