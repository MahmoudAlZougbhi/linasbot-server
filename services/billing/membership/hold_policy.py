"""Pending-settlement policy. Live meter is credits only."""

from __future__ import annotations

from services.billing.membership.pending_settlement import BillingPolicy


def hold_billing_policy(*, leftover_reservation_id: str | None) -> BillingPolicy:
    _ = leftover_reservation_id
    return "legacy_credits"
