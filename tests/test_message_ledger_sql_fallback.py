"""Message ledger uses process-local lots/holds when SQL has no matching row."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest

from services.membership.lot_window import current_period_id
from services.membership.message_ledger import (
    InsufficientMessages,
    LedgerSnapshot,
    expire_included_before,
    grant_lot,
    known_ledger_tenant_ids,
    list_stale_reserved,
    remaining_messages,
    reserve,
    reset_ledger_for_tests,
    reverse,
    settle,
    snapshot,
)


def _sql_session():
    @contextmanager
    def _session():
        yield object()

    return _session


def test_known_ledger_tenants_union_memory_and_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(tenant_id="mem-led", lot_id="inc", kind="included", period_id=current_period_id(), amount=1)
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_known_tenant_ids",
        lambda _s: ["sql-led"],
    )
    assert known_ledger_tenant_ids() == ["mem-led", "sql-led"]


def test_snapshot_includes_memory_lots_when_sql_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(tenant_id="mem-snap", lot_id="inc", kind="included", period_id=current_period_id(), amount=7)
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_snapshot",
        lambda _s, tid: LedgerSnapshot(tenant_id=tid),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_reservations",
        lambda _s, tenant_id=None: [],
    )
    assert snapshot("mem-snap").remaining == 7
    assert remaining_messages("mem-snap") == 7


def test_settle_uses_memory_hold_when_sql_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(tenant_id="mem-hold", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    reserve(tenant_id="mem-hold", operation_id="mid-mem", response_class="generated_ai")
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    def _missing(*_args, **kwargs):
        raise KeyError(kwargs.get("operation_id") or "mid-mem")

    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr("services.membership.message_ledger_pg.pg_settle", _missing)
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_snapshot",
        lambda _s, tid: LedgerSnapshot(tenant_id=tid),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_reservations",
        lambda _s, tenant_id=None: [],
    )
    settled = settle(tenant_id="mem-hold", operation_id="mid-mem", accepted=True)
    assert settled.status == "settled"
    assert remaining_messages("mem-hold") == 1


def test_reverse_uses_memory_hold_when_sql_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(tenant_id="mem-rev", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    reserve(tenant_id="mem-rev", operation_id="mid-rev", response_class="generated_ai")
    settle(tenant_id="mem-rev", operation_id="mid-rev", accepted=True)
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    def _missing(*_args, **kwargs):
        raise KeyError(kwargs.get("operation_id") or "mid-rev")

    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr("services.membership.message_ledger_pg.pg_reverse", _missing)
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_snapshot",
        lambda _s, tid: LedgerSnapshot(tenant_id=tid),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_reservations",
        lambda _s, tenant_id=None: [],
    )
    reversed_hold = reverse(tenant_id="mem-rev", operation_id="mid-rev")
    assert reversed_hold.status == "reversed"
    assert remaining_messages("mem-rev") == 2


def test_reserve_uses_memory_lot_when_sql_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(tenant_id="mem-res", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_reserve",
        lambda *_a, **_k: (_ for _ in ()).throw(InsufficientMessages("mem-res", 0)),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_snapshot",
        lambda _s, tid: LedgerSnapshot(tenant_id=tid),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_reservations",
        lambda _s, tenant_id=None: [],
    )
    held = reserve(tenant_id="mem-res", operation_id="mid-res", response_class="generated_ai")
    assert held.status == "reserved"
    assert remaining_messages("mem-res") == 1


def test_expire_included_also_clears_memory_lots(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(tenant_id="mem-exp", lot_id="old", kind="included", period_id="2026-01", amount=4)
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr("services.membership.message_ledger_pg.pg_expire_included_before", lambda *_a, **_k: 0)
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_snapshot",
        lambda _s, tid: LedgerSnapshot(tenant_id=tid),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_reservations",
        lambda _s, tenant_id=None: [],
    )
    assert expire_included_before("mem-exp", "2026-09") == 1
    assert remaining_messages("mem-exp") == 0


def test_list_stale_reserved_unions_memory_when_sql_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.membership import message_ledger as ledger

    reset_ledger_for_tests()
    grant_lot(tenant_id="stale-mem", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    reserve(tenant_id="stale-mem", operation_id="mid-stale", response_class="generated_ai")
    key = ledger._res_key("stale-mem", "mid-stale")
    ledger._RESERVATIONS[key].created_at = "2020-01-01T00:00:00+00:00"
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_stale_reserved",
        lambda *_a, **_k: [],
    )
    items = list_stale_reserved(older_than=datetime.now(timezone.utc), limit=50)
    assert any(item.operation_id == "mid-stale" for item in items)


def test_revoke_purchased_also_clears_memory_lots(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_ledger_for_tests()
    grant_lot(
        tenant_id="mem-revk",
        lot_id="buy:txn-1",
        kind="purchased",
        period_id="txn-1",
        amount=5,
        expires=False,
        catalog_version="txn-1",
    )
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.message_ledger._pg_session", _sql_session())
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_revoke_purchased",
        lambda *_a, **_k: {"revoked": False, "lot_ids": [], "remaining_cleared": 0, "reservations_released": 0},
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_snapshot",
        lambda _s, tid: LedgerSnapshot(tenant_id=tid),
    )
    monkeypatch.setattr(
        "services.membership.message_ledger_pg.pg_list_reservations",
        lambda _s, tenant_id=None: [],
    )
    from services.membership.message_ledger import revoke_purchased

    out = revoke_purchased(tenant_id="mem-revk", transaction_id="txn-1")
    assert out["revoked"] is True
    assert remaining_messages("mem-revk") == 0
