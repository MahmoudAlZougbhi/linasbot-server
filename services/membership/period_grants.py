"""Issue included message lots from the current paid plan. No credit conversion."""

from __future__ import annotations

from services.membership.lot_window import current_period_id

__all__ = ["current_period_id", "ensure_included_grant"]
from services.membership.message_catalog import MESSAGE_CATALOG_VERSION, require_message_plan
from services.membership.message_flags import message_billing_enabled
from services.membership.message_ledger import expire_included_before, grant_lot


def ensure_included_grant(tenant_id: str) -> None:
    if not message_billing_enabled():
        return
    tid = (tenant_id or "").strip()
    if not tid:
        return
    expire_included_before(tid, current_period_id())
    try:
        from services.entitlements_service import entitlements_store

        ent = entitlements_store.get(tid)
        plan_id = str(ent.plan_id or "").strip().lower()
        status = str(ent.status or "").strip().lower()
    except Exception:
        return
    if status in {"refunded", "revoked", "expired"}:
        expire_included_before(tid, "")
        return
    if plan_id in {"", "none", "free"} or status not in {"active", "trial", "grace"}:
        return
    try:
        require_message_plan(plan_id)
        from services.membership.catalog_admin import effective_included_messages

        amount = effective_included_messages(plan_id)
    except KeyError:
        return
    if amount is None:
        return
    period = current_period_id()
    grant_lot(
        tenant_id=tid,
        lot_id=f"{tid}:{plan_id}:{period}",
        kind="included",
        period_id=period,
        amount=int(amount),
        expires=True,
        catalog_version=MESSAGE_CATALOG_VERSION,
    )
