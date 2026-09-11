"""Message ledger isolation and last-unit concurrency. No invented conversion."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from services.membership.lot_window import current_period_id
from services.membership.message_ledger import (
    InsufficientMessages,
    grant_lot,
    remaining_messages,
    reserve,
    reset_ledger_for_tests,
    snapshot,
)


@pytest.fixture(autouse=True)
def _memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_ledger_for_tests()


def test_tenants_do_not_share_lots() -> None:
    grant_lot(
        tenant_id="alpha",
        lot_id="a-inc",
        kind="included",
        period_id=current_period_id(),
        amount=5,
    )
    grant_lot(
        tenant_id="beta",
        lot_id="b-inc",
        kind="included",
        period_id=current_period_id(),
        amount=3,
    )
    reserve(tenant_id="alpha", operation_id="gen-a", response_class="generated_ai")
    assert remaining_messages("alpha") == 4
    assert remaining_messages("beta") == 3
    assert snapshot("beta").reserved == 0


def test_last_unit_has_one_winner() -> None:
    grant_lot(
        tenant_id="race",
        lot_id="one",
        kind="included",
        period_id=current_period_id(),
        amount=1,
    )
    winners: list[str] = []
    errors: list[InsufficientMessages] = []

    def claim(operation_id: str) -> None:
        try:
            reserve(tenant_id="race", operation_id=operation_id, response_class="generated_ai")
            winners.append(operation_id)
        except InsufficientMessages as exc:
            errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(claim, ("op-a", "op-b")))
    assert len(winners) == 1
    assert len(errors) == 1
    snap = snapshot("race")
    assert snap.reserved == 1
    assert snap.remaining == 0
