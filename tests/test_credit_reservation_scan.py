"""Leftover-credit scan uses the live credit ledger. Stale jsonl cannot reopen a hold."""

from __future__ import annotations

from contextlib import contextmanager

import pytest


def test_seed_uses_postgres_even_when_open_list_is_empty(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import time

    from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
    from services.membership.credit_reservation_scan import seed_from_known_ledgers

    reset_credit_reservation_index_for_tests()
    ledger = tmp_path / "credit_ledger"
    ledger.mkdir()
    monkeypatch.setattr("services.membership.credit_reservation_scan._DATA_ROOT", tmp_path)
    monkeypatch.setattr("services.membership.credit_reservation_scan.known_credit_tenant_ids", lambda: ["pg-sot"])
    monkeypatch.setattr("services.billing_backend.billing_uses_postgres", lambda: True)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.billing_backend.require_billing_pg_session", _session)
    monkeypatch.setattr("services.credit_ledger_pg_store.list_open_leftover_reservations", lambda *_a, **_k: [])
    rid = "e" * 32
    (ledger / "pg-sot.jsonl").write_text(
        json.dumps(
            {
                "id": rid,
                "tenant_id": "pg-sot",
                "op": "reserve",
                "credits": 1,
                "request_id": "wa:stale",
                "operation_type": "whatsapp_customer_reply",
                "created_at": time.time() - 7200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert seed_from_known_ledgers() == 0
    assert open_counts(tenant_id="pg-sot")["open"] == 0


def test_open_counts_skip_memory_row_already_closed_in_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.membership import credit_reservation_index as index
    from services.membership.credit_reservation_index import OpenCreditReservation, open_counts, record_open

    record_open(
        tenant_id="idx-closed",
        reservation_id="rid-closed",
        request_id="wa:closed",
        operation_type="whatsapp",
    )
    monkeypatch.setattr(index, "_list_pg", lambda **_k: [])
    monkeypatch.setattr(index, "_sql_known_ids", lambda **_k: {"rid-closed"})
    assert open_counts(tenant_id="idx-closed")["open"] == 0
    sql_open = OpenCreditReservation(
        reservation_id="rid-sql-open",
        tenant_id="idx-closed",
        request_id="wa:sql-open",
        operation_type="whatsapp",
        created_at="2026-01-01T00:00:00+00:00",
        state="reserved",
    )
    monkeypatch.setattr(index, "_list_pg", lambda **_k: [sql_open])
    monkeypatch.setattr(index, "_sql_known_ids", lambda **_k: {"rid-closed", "rid-sql-open"})
    assert open_counts(tenant_id="idx-closed")["open"] == 1


def test_record_open_reopens_settled_index_row() -> None:
    from services.membership.credit_reservation_index import (
        mark_closed,
        open_counts,
        record_open,
        reset_credit_reservation_index_for_tests,
    )

    reset_credit_reservation_index_for_tests()
    record_open(
        tenant_id="reopen-shop",
        reservation_id="rid-reopen",
        request_id="wa:reopen",
        operation_type="whatsapp",
    )
    mark_closed("rid-reopen", state="settled")
    assert open_counts(tenant_id="reopen-shop")["open"] == 0
    item = record_open(
        tenant_id="reopen-shop",
        reservation_id="rid-reopen",
        request_id="wa:reopen",
        operation_type="whatsapp",
    )
    assert item is not None
    assert item.state == "reserved"
    assert open_counts(tenant_id="reopen-shop")["open"] == 1
    mark_closed("rid-reopen", state="pending_settlement")
    kept = record_open(
        tenant_id="reopen-shop",
        reservation_id="rid-reopen",
        request_id="wa:reopen",
        operation_type="whatsapp",
    )
    assert kept is not None
    assert kept.state == "pending_settlement"
    assert open_counts(tenant_id="reopen-shop")["open"] == 0


def test_sql_miss_does_not_revive_stale_reserved_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership import credit_reservation_index as index
    from services.membership.credit_reservation_index import record_open, reset_credit_reservation_index_for_tests

    reset_credit_reservation_index_for_tests()
    record_open(
        tenant_id="sql-miss",
        reservation_id="rid-miss",
        request_id="wa:miss",
        operation_type="whatsapp",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr(index, "_memory_forced", lambda: False)
    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.pg_get", lambda *_a, **_k: None)
    assert index._get("rid-miss") is None
    persisted: list[str] = []
    monkeypatch.setattr(index, "_persist", lambda row: persisted.append(row.state))
    again = record_open(
        tenant_id="sql-miss",
        reservation_id="rid-miss",
        request_id="wa:miss",
        operation_type="whatsapp",
    )
    assert again is not None
    assert again.state == "reserved"
    assert persisted == ["reserved"]


def test_hydrate_skips_disk_reserved_when_sql_already_has_id(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    from contextlib import contextmanager

    from services.membership import credit_reservation_index as index
    from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests

    reset_credit_reservation_index_for_tests()
    folder = tmp_path / "credit_reservation_index"
    folder.mkdir()
    (folder / "rid-disk.json").write_text(
        json.dumps(
            {
                "reservation_id": "rid-disk",
                "tenant_id": "disk-shop",
                "request_id": "wa:disk",
                "operation_type": "whatsapp",
                "created_at": "2026-01-01T00:00:00+00:00",
                "state": "reserved",
            }
        ),
        encoding="utf-8",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr(index, "_root", lambda: folder)
    monkeypatch.setattr(index, "_memory_forced", lambda: False)
    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.pg_list", lambda *_a, **_k: [])
    monkeypatch.setattr(
        "services.membership.credit_reservation_index_pg.pg_reservation_ids",
        lambda *_a, **_k: {"rid-disk"},
    )
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.pg_get", lambda *_a, **_k: object())
    index._ITEMS.clear()
    index._HYDRATED = False
    index._hydrate()
    assert "rid-disk" not in index._ITEMS
    assert open_counts(tenant_id="disk-shop")["open"] == 0


def test_seed_does_not_reopen_capture_keyed_by_request_id(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    import json
    import time

    from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
    from services.membership.credit_reservation_scan import leftover_closed, seed_from_known_ledgers

    reset_credit_reservation_index_for_tests()
    ledger = tmp_path / "credit_ledger"
    ledger.mkdir()
    monkeypatch.setattr("services.membership.credit_reservation_scan._DATA_ROOT", tmp_path)
    monkeypatch.setattr("services.membership.credit_reservation_scan.known_credit_tenant_ids", lambda: ["req-cap"])
    rid = "f" * 32
    now = time.time() - 7200
    (ledger / "req-cap.jsonl").write_text(
        json.dumps(
            {
                "id": rid,
                "tenant_id": "req-cap",
                "op": "reserve",
                "credits": 1,
                "request_id": "wa:inbound-mid",
                "operation_type": "whatsapp_customer_reply",
                "created_at": now,
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "g" * 32,
                "tenant_id": "req-cap",
                "op": "capture",
                "credits": 1,
                "request_id": "wa:inbound-mid",
                "operation_type": "capture",
                "created_at": now + 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert leftover_closed(rid, "wa:inbound-mid", {"wa:inbound-mid"})
    assert seed_from_known_ledgers() == 0
    assert open_counts(tenant_id="req-cap")["open"] == 0
