"""Pending-settlement policy for leftover credits vs message units.

Never tag a message-ledger hold as leftover credits. Age still never refunds.
"""

from __future__ import annotations

from services.membership.pending_settlement import BillingPolicy


def hold_billing_policy(*, leftover_reservation_id: str | None) -> BillingPolicy:
    if leftover_reservation_id:
        return "legacy_credits"
    from services.membership.message_flags import message_billing_enabled

    return "message_units" if message_billing_enabled() else "legacy_credits"
