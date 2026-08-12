"""Financial N→1 invariant helpers for HA / Apple credit tests."""

from __future__ import annotations

from typing import Any


def unexplained_financial_delta(
    *,
    expected_net_credits: int,
    observed_balance_delta: int,
    known_adjustments: int = 0,
) -> int:
    """Return abs unexplained delta (must be 0 for PASS).

    ``known_adjustments`` covers documented debt floors / admin adjustments.
    """
    explained = int(expected_net_credits) + int(known_adjustments)
    return abs(int(observed_balance_delta) - explained)


def summarize_financial_case(details: dict[str, Any]) -> dict[str, Any]:
    delta = unexplained_financial_delta(
        expected_net_credits=int(details.get("expected_net_credits") or 0),
        observed_balance_delta=int(details.get("observed_balance_delta") or 0),
        known_adjustments=int(details.get("known_adjustments") or 0),
    )
    return {**details, "unexplained_financial_delta": delta}
