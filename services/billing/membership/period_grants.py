"""Issue included message lots for the current UTC month. Unused included lots expire."""

from __future__ import annotations

from services.billing.membership.lot_window import current_period_id

__all__ = ["current_period_id", "ensure_included_grant"]


def ensure_included_grant(tenant_id: str) -> None:
    tid = (tenant_id or "").strip()
    if not tid:
        return
    from services.billing.entitlements_service import entitlements_store
    from services.billing.membership.catalog_admin import effective_included_messages
    from services.billing.membership.message_catalog import MESSAGE_CATALOG_VERSION
    from services.billing.membership.message_ledger import expire_included_before, grant_lot

    try:
        ent = entitlements_store.get(tid)
    except Exception:
        return
    plan_id = str(getattr(ent, "plan_id", "") or "").strip().lower()
    if not plan_id or plan_id in {"none", "free"}:
        return
    status = str(getattr(ent, "status", "") or "").strip().lower()
    if status not in {"active", "trial", "grace"}:
        expire_included_before(tid, "__none__")
        return
    included = effective_included_messages(plan_id)
    if included is None or int(included) <= 0:
        return
    period_id = current_period_id()
    expire_included_before(tid, period_id)
    grant_lot(
        tenant_id=tid,
        lot_id=f"{tid}:included:{period_id}",
        kind="included",
        period_id=period_id,
        amount=int(included),
        expires=True,
        catalog_version=MESSAGE_CATALOG_VERSION,
    )
