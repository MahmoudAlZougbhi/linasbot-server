"""Included message lots are not issued. Subscription grants credits elsewhere."""

from __future__ import annotations

from services.billing.membership.lot_window import current_period_id

__all__ = ["current_period_id", "ensure_included_grant"]


def ensure_included_grant(tenant_id: str) -> None:
    _ = tenant_id
    return
