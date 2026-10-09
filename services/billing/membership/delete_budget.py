"""Separate daily cap for free deletes. Not the AI Setup edit budget."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from services.billing.membership.daily_edits import DailyEditDecision, DailyEditLimitError

DELETE_DAILY_LIMIT = 1000
_LOCK = threading.Lock()
_USED: dict[str, dict[str, int]] = {}


class DeleteBudgetError(DailyEditLimitError):
    def __init__(self, decision: DailyEditDecision) -> None:
        super().__init__(decision)
        self.code = "DELETE_DAILY_LIMIT"


def reset_delete_budget_for_tests() -> None:
    with _LOCK:
        _USED.clear()


def reserve_delete(tenant_id: str, *, limit: int = DELETE_DAILY_LIMIT) -> None:
    tid = tenant_id.strip()
    day = datetime.now(UTC).date().isoformat()
    with _LOCK:
        used = _USED.setdefault(tid, {}).get(day, 0)
        if used >= limit:
            raise DeleteBudgetError(
                DailyEditDecision(
                    allow=False,
                    used=used,
                    reserved=0,
                    remaining=0,
                    limit=limit,
                    window_id=day,
                    reset_at=day,
                    reason="delete_budget",
                )
            )
        _USED[tid][day] = used + 1
