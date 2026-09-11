"""Isolated leftover/message settlement: confirmed send never frees a failed capture."""

from __future__ import annotations

import pytest

from services.customer_ai.leftover_reserve import (
    capture_leftover_reply,
    leftover_policy_for,
    release_leftover_reply,
    reserve_leftover_reply,
    reset_leftover_pins_for_tests,
)
from services.membership.pending_settlement import (
    get_pending,
    list_pending,
    pending_counts,
    record_pending_after_send,
    reset_pending_settlements_for_tests,
)
from services.membership.reservation_reconcile import run_reservation_reconcile


class _Ledger:
    def __init__(self) -> None:
        self.captures = 0
        self.releases = 0
        self.fail_capture = True

    def reserve(self, **_kwargs):
        return "rid-hold-1"

    def capture(self, **_kwargs):
        if self.fail_capture:
            raise RuntimeError("capture_down")
        self.captures += 1
        return {"op": "capture"}

    def release(self, **_kwargs):
        self.releases += 1
        return {"op": "release"}


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    reset_pending_settlements_for_tests()
    reset_leftover_pins_for_tests()
    from services.membership.credit_reservation_index import reset_credit_reservation_index_for_tests

    reset_credit_reservation_index_for_tests()


def test_failed_capture_after_send_keeps_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    rid = reserve_leftover_reply(tenant_id="shop-a", request_id="omni:1", operation_type="omni")
    assert rid == "rid-hold-1"
    assert leftover_policy_for("shop-a", "omni:1") == "legacy_credits"
    assert capture_leftover_reply("shop-a", rid, model_provider="whatsapp") is False
    assert ledger.releases == 0
    pending = list_pending(states=("pending_settlement",))
    assert len(pending) == 1
    assert pending[0].send_status == "sent"
    assert pending[0].billing_policy == "legacy_credits"


def test_reconcile_settles_once_and_does_not_double_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    ledger.fail_capture = False
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    record_pending_after_send(
        tenant_id="shop-a",
        reservation_id="rid-hold-1",
        operation_id="omni:1",
        billing_policy="legacy_credits",
        provider_message_id="wamid-1",
        channel="whatsapp",
    )
    first = run_reservation_reconcile()
    assert first["settled"] == 1
    assert ledger.captures == 1
    second = run_reservation_reconcile()
    assert second["settled"] == 0
    assert ledger.captures == 1
    assert pending_counts()["pending_settlement"] == 0
    assert leftover_policy_for("shop-a", "omni:1", "rid-hold-1") is None


def test_unknown_stale_reservation_is_unresolved_not_released(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timedelta, timezone

    from services.membership.lot_window import current_period_id
    from services.membership.message_ledger import (
        grant_lot,
        list_reservations,
        remaining_messages,
        reserve,
        reset_ledger_for_tests,
    )

    reset_ledger_for_tests()
    grant_lot(tenant_id="shop-b", lot_id="inc", kind="included", period_id=current_period_id(), amount=3)
    reserve(tenant_id="shop-b", operation_id="unknown-1", response_class="generated_ai")
    held = next(item for item in list_reservations("shop-b") if item.operation_id == "unknown-1")
    held.created_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    result = run_reservation_reconcile()
    assert result["ran"] is True
    assert remaining_messages("shop-b") == 2
    assert any(item.state == "unresolved" for item in list_pending())


def test_reconcile_unpins_leftover_after_failed_capture(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    rid = reserve_leftover_reply(tenant_id="shop-retry", request_id="omni:retry", operation_type="omni")
    assert capture_leftover_reply("shop-retry", rid, model_provider="whatsapp") is False
    assert leftover_policy_for("shop-retry", "omni:retry") == "legacy_credits"
    ledger.fail_capture = False
    result = run_reservation_reconcile()
    assert result["settled"] == 1
    assert leftover_policy_for("shop-retry", "omni:retry", rid or "") is None


def test_unused_release_only_when_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    rid = reserve_leftover_reply(tenant_id="shop-c", request_id="omni:miss", operation_type="omni")
    release_leftover_reply("shop-c", rid)
    assert ledger.releases == 1
    assert any(item.state == "released" for item in list_pending(states=("released",)))


def test_policy_pin_blocks_message_debit_after_flag_flip(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    reserve_leftover_reply(
        tenant_id="pin-shop",
        request_id="evt-pin",
        operation_type="omni",
        pin_ids=("evt-pin",),
    )
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    from services.customer_ai.billing import apply_message_billing
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
    from services.customer_ai.contracts.turn import CustomerTurn
    from services.membership.message_ledger import remaining_messages, reset_ledger_for_tests

    reset_ledger_for_tests()
    result = apply_message_billing(
        CustomerTurn(tenant_id="pin-shop", conversation_id="c1", event_ids=["evt-pin"]),
        TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="Hi")],
            ),
            ai_called=True,
            extra={"phase": "generate"},
        ),
    )
    assert result.extra["billing_policy"] == "legacy_credits"
    assert remaining_messages("pin-shop") == 0


def test_leftover_pin_ids_persist_as_candidate_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    rid = reserve_leftover_reply(
        tenant_id="alias-shop",
        request_id="evt-alias",
        operation_type="omni",
        pin_ids=("conv-alias",),
    )
    held = get_pending("alias-shop", rid, "evt-alias")
    assert held is not None
    assert "conv-alias" in (held.extra.get("candidate_ids") or [])
    from services.customer_ai.leftover_reserve import _PINS

    _PINS.clear()
    assert leftover_policy_for("alias-shop", "conv-alias") == "legacy_credits"
    release_leftover_reply("alias-shop", rid)
    assert leftover_policy_for("alias-shop", "conv-alias") is None
    assert leftover_policy_for("alias-shop", "evt-alias") is None


def test_capture_failure_keeps_existing_candidate_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.membership.reservation_reconcile import hold_failed_capture_after_send

    ledger = _Ledger()
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    rid = reserve_leftover_reply(
        tenant_id="keep-shop",
        request_id="evt-keep",
        operation_type="omni",
        pin_ids=("conv-keep",),
    )
    hold_failed_capture_after_send(
        tenant_id="keep-shop",
        reservation_id=rid,
        operation_id="evt-keep",
        billing_policy="legacy_credits",
        provider_message_id="wa-keep",
        channel="omni",
    )
    held = get_pending("keep-shop", rid, "evt-keep")
    assert held is not None
    aliases = held.extra.get("candidate_ids") or []
    assert "conv-keep" in aliases
    assert "wa-keep" in aliases
    assert leftover_policy_for("keep-shop", "conv-keep") == "legacy_credits"


def test_leftover_policy_unpins_when_sql_has_no_active_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai import leftover_reserve as leftover
    from services.membership import pending_settlement as pending

    leftover._PINS["stale-shop:mid-stale"] = "legacy_credits"
    leftover._PINS["stale-shop:conv-stale"] = "legacy_credits"
    monkeypatch.setattr(pending, "policy_for_operation", lambda *_a, **_k: None)
    monkeypatch.setattr(pending, "_sql_ready", lambda: True)
    assert leftover_policy_for("stale-shop", "mid-stale", "conv-stale") is None
    assert "stale-shop:mid-stale" not in leftover._PINS
    assert "stale-shop:conv-stale" not in leftover._PINS


def test_policy_for_operation_uses_sql_over_stale_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership import pending_settlement as pending
    from services.membership.pending_settlement import policy_for_operation, upsert

    upsert(
        tenant_id="stale-shop",
        reservation_id="rid-stale",
        operation_id="mid-stale",
        billing_policy="legacy_credits",
        state="reserved",
        extra={"candidate_ids": ["mid-stale", "conv-stale"]},
    )
    monkeypatch.setattr(pending, "_memory_forced", lambda: False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.pending_settlement_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.pending_settlement_pg.pg_policy_for", lambda *_a, **_k: None)
    assert policy_for_operation("stale-shop", "mid-stale", "conv-stale") is None


def test_known_settlement_tenants_union_memory_and_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.pending_settlement import known_settlement_tenant_ids, upsert

    upsert(
        tenant_id="mem-settle",
        reservation_id="rid-mem",
        operation_id="mid-mem",
        billing_policy="message_units",
        state="reserved",
    )
    monkeypatch.setattr("services.membership.pending_settlement._memory_forced", lambda: False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.pending_settlement_pg.table_ready", lambda _s: True)
    monkeypatch.setattr(
        "services.membership.pending_settlement_pg.pg_tenant_ids",
        lambda _s: ["sql-settle"],
    )
    assert known_settlement_tenant_ids() == ["mem-settle", "sql-settle"]


def test_list_pending_unions_memory_and_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.pending_settlement import PendingSettlement, list_pending, upsert

    upsert(
        tenant_id="mem-pend",
        reservation_id="rid-mem",
        operation_id="mid-mem",
        billing_policy="message_units",
        state="reserved",
    )
    sql_item = PendingSettlement(
        settlement_id="sql-pend:rid-sql",
        tenant_id="sql-pend",
        reservation_id="rid-sql",
        operation_id="mid-sql",
        billing_policy="message_units",
        state="pending_settlement",
        created_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.pending_settlement_pg.table_ready", lambda _s: True)
    monkeypatch.setattr(
        "services.membership.pending_settlement_pg.pg_list",
        lambda *_a, **_k: [sql_item],
    )
    tenants = {item.tenant_id for item in list_pending()}
    assert "mem-pend" in tenants
    assert "sql-pend" in tenants


def test_list_pending_skips_memory_row_already_known_in_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.pending_settlement import list_pending, upsert

    upsert(
        tenant_id="stale-pend",
        reservation_id="rid-stale",
        operation_id="mid-stale",
        billing_policy="legacy_credits",
        state="reserved",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.pending_settlement_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.pending_settlement_pg.pg_list", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "services.membership.pending_settlement_pg.pg_settlement_ids",
        lambda *_a, **_k: {"stale-pend:rid-stale"},
    )
    assert list_pending(tenant_id="stale-pend", states=("reserved",)) == []


def test_pending_counts_union_memory_and_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.pending_settlement import pending_counts, upsert

    upsert(
        tenant_id="mem-count",
        reservation_id="rid-mem-c",
        operation_id="mid-mem-c",
        billing_policy="message_units",
        state="reserved",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.pending_settlement_pg.table_ready", lambda _s: True)
    monkeypatch.setattr(
        "services.membership.pending_settlement_pg.pg_counts",
        lambda *_a, **_k: {"reserved": 0, "pending_settlement": 1, "settled": 0, "released": 0, "unresolved": 0},
    )
    monkeypatch.setattr("services.membership.pending_settlement_pg.pg_settlement_ids", lambda *_a, **_k: {"sql-count:rid"})
    counts = pending_counts()
    assert counts["reserved"] == 1
    assert counts["pending_settlement"] == 1


def test_capture_leftover_with_alias_settles_original_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    ledger = _Ledger()
    ledger.fail_capture = False
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    rid = reserve_leftover_reply(
        tenant_id="alias-cap",
        request_id="wa:inbound",
        operation_type="whatsapp",
        pin_ids=("conv-cap",),
    )
    assert leftover_policy_for("alias-cap", "conv-cap") == "legacy_credits"
    assert capture_leftover_reply(
        "alias-cap",
        rid,
        model_provider="whatsapp",
        operation_id="conv-cap",
        provider_message_id="wamid-cap",
    )
    held = get_pending("alias-cap", rid or "", "wa:inbound")
    assert held is not None
    assert held.state == "settled"
    assert held.operation_id == "wa:inbound"
    assert leftover_policy_for("alias-cap", "conv-cap", "wa:inbound") is None


def test_get_pending_matches_conversation_alias() -> None:
    from services.membership.pending_settlement import upsert

    upsert(
        tenant_id="alias-shop",
        reservation_id="rid-alias",
        operation_id="mid-alias",
        billing_policy="legacy_credits",
        state="reserved",
        extra={"candidate_ids": ["mid-alias", "conv-alias"]},
    )
    held = get_pending("alias-shop", "conv-alias")
    assert held is not None
    assert held.reservation_id == "rid-alias"
    assert get_pending("alias-shop", "", "conv-alias") is not None


def test_hydrate_skips_disk_reserved_when_sql_already_has_id(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from contextlib import contextmanager

    from services.membership import pending_settlement as pending
    from services.membership.pending_settlement import list_pending

    folder = tmp_path / "pending_settlements"
    folder.mkdir()
    sid = "disk-pend:rid-disk"
    (folder / "disk.json").write_text(
        json.dumps(
            {
                "settlement_id": sid,
                "tenant_id": "disk-pend",
                "reservation_id": "rid-disk",
                "operation_id": "mid-disk",
                "billing_policy": "legacy_credits",
                "state": "reserved",
            }
        ),
        encoding="utf-8",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr(pending, "_root", lambda: folder)
    monkeypatch.setattr(pending, "_memory_forced", lambda: False)
    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.pending_settlement_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.pending_settlement_pg.pg_list", lambda *_a, **_k: [])
    monkeypatch.setattr("services.membership.pending_settlement_pg.pg_settlement_ids", lambda *_a, **_k: {sid})
    pending._ITEMS.clear()
    pending._HYDRATED = False
    pending._hydrate()
    assert sid not in pending._ITEMS
    assert list_pending(tenant_id="disk-pend", states=("reserved",)) == []
