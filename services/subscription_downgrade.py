"""Schedule subscription downgrades at period end (never mid-cycle)."""

from __future__ import annotations

import time
from typing import Any

from services.entitlements_service import entitlements_store
from services.membership.plan_catalog import PUBLIC_PLAN_IDS, require_plan
from services.plan_economics import PLAN_PRICES_USD

PLAN_RANK: dict[str, int] = {plan_id: idx for idx, plan_id in enumerate(PUBLIC_PLAN_IDS)}


def plan_rank(plan_id: str | None) -> int | None:
    pid = (plan_id or "").strip().lower()
    if pid not in PLAN_RANK:
        return None
    return PLAN_RANK[pid]


def is_downgrade(current_plan_id: str | None, target_plan_id: str | None) -> bool:
    cur = plan_rank(current_plan_id)
    nxt = plan_rank(target_plan_id)
    if cur is None or nxt is None:
        return False
    return nxt < cur


def is_upgrade(current_plan_id: str | None, target_plan_id: str | None) -> bool:
    cur = plan_rank(current_plan_id)
    nxt = plan_rank(target_plan_id)
    if cur is None or nxt is None:
        return False
    return nxt > cur


def clear_pending_downgrade(tenant_id: str) -> None:
    ent = entitlements_store.get(tenant_id)
    if not ent.pending_plan_id and ent.pending_plan_effective_at is None:
        return
    ent.pending_plan_id = None
    ent.pending_plan_effective_at = None
    entitlements_store.save(ent)


def schedule_pending_downgrade(
    *,
    tenant_id: str,
    pending_plan_id: str,
    effective_at: float | None = None,
) -> dict[str, Any]:
    """Record a downgrade that takes effect at the next renewal (not immediately)."""
    pid = (pending_plan_id or "").strip().lower()
    if pid not in PLAN_PRICES_USD:
        raise ValueError(f"Unknown plan: {pending_plan_id}")

    ent = entitlements_store.get(tenant_id)
    current = (ent.plan_id or "").strip().lower()
    if current not in PLAN_PRICES_USD:
        raise ValueError("Active subscription required to schedule downgrade")
    if not is_downgrade(current, pid):
        raise ValueError("Target plan is not a downgrade from the current plan")

    when = effective_at
    if when is None:
        when = ent.current_period_end
    if when is None:
        when = time.time() + 30 * 86400

    ent.pending_plan_id = pid
    ent.pending_plan_effective_at = float(when)
    entitlements_store.save(ent)
    return pending_downgrade_public(ent)


def pending_downgrade_public(ent: Any) -> dict[str, Any] | None:
    pid = (getattr(ent, "pending_plan_id", None) or "").strip().lower()
    effective = getattr(ent, "pending_plan_effective_at", None)
    if not pid or pid not in PLAN_PRICES_USD or effective is None:
        return None
    try:
        display_name = require_plan(pid).display_name
    except KeyError:
        display_name = pid
    return {
        "plan_id": pid,
        "display_name": display_name,
        "effective_at": float(effective),
    }


def should_schedule_instead_of_apply(
    *,
    current_plan_id: str | None,
    target_plan_id: str,
    status: str,
    notification_type: str | None = None,
) -> bool:
    """True when a lower plan purchase must not replace the active plan mid-cycle."""
    if (status or "").lower() != "active":
        return False
    if not is_downgrade(current_plan_id, target_plan_id):
        return False
    ntype = (notification_type or "").strip().upper()
    if ntype in {"DID_RENEW", "SUBSCRIBED", "INITIAL_BUY", "OFFER_REDEEMED"}:
        return False
    current = (current_plan_id or "").strip().lower()
    return current in PLAN_PRICES_USD
