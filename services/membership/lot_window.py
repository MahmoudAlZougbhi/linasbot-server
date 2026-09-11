"""Included lots expire by UTC calendar month. Purchased lots do not."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def current_period_id() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def lot_is_live(lot: Any, *, period_id: str | None = None) -> bool:
    if not getattr(lot, "expires", True):
        return True
    return str(getattr(lot, "period_id", "") or "") == (period_id or current_period_id())
