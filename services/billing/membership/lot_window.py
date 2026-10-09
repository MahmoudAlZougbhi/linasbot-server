"""Included lots expire by UTC calendar month. Purchased lots do not."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def current_period_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def lot_is_live(lot: Any, *, period_id: str | None = None) -> bool:
    from services.platform.feature_flags import flag_enabled

    if flag_enabled("period_balances"):
        from services.billing.membership.balances import lot_is_live_now

        return lot_is_live_now(lot)
    if not getattr(lot, "expires", True):
        return True
    return str(getattr(lot, "period_id", "") or "") == (period_id or current_period_id())
