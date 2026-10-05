"""Tool names Terra must not offer on this turn."""

from __future__ import annotations

from typing import Any

from services.brain.contracts.turn import CustomerTurn


def skip_tools_for_turn(turn: CustomerTurn, extra: dict[str, Any] | None) -> set[str]:
    skip: set[str] = set()
    if str(getattr(turn, "surface", "") or "") == "comment":
        skip.add("start_request")
    if (extra or {}).get("pending_human_escalate"):
        skip.add("escalate_to_human")
    return skip
