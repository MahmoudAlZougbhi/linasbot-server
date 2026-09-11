"""Legacy leftover capture waits for send evidence; stale holds stay unresolved."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from inspect import getsource

from services.ai_reply_turn_runtime import (
    finalize_delivery,
    on_ai_generated,
    settle_after_outbound,
    settle_reserved_credits,
)
from services.customer_ai.leftover_reserve import reset_leftover_pins_for_tests
from services.membership.credit_reservation_index import (
    list_stale_open,
    record_open,
    reset_credit_reservation_index_for_tests,
)
from services.membership.pending_settlement import list_pending, reset_pending_settlements_for_tests
from services.membership.reservation_reconcile import watch_stale_legacy_credits


def setup_function() -> None:
    reset_leftover_pins_for_tests()
    reset_credit_reservation_index_for_tests()
    reset_pending_settlements_for_tests()


def test_on_ai_generated_does_not_capture(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.capture_after_reply_persisted",
        lambda *a, **k: calls.append("capture"),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.persist_generated_reply", lambda *a, **k: None)
    user_data = {"_logical_reply_id": "lid-1", "tenant_id": "shop"}
    on_ai_generated({"user_data": user_data, "bot_reply_text": "hello"})
    assert user_data["_reply_ready"] is True
    assert user_data.get("_credit_captured_for_turn") is not True
    assert calls == []


def test_settle_with_reply_captures_after_send(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.capture_after_reply_persisted",
        lambda *a, **k: calls.append("capture"),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.persist_generated_reply", lambda *a, **k: None)
    monkeypatch.setattr("services.customer_ai.billing.settle_after_send", lambda **k: calls.append("settle"))
    user_data = {"_logical_reply_id": "lid-2", "tenant_id": "shop"}
    settle_reserved_credits(user_data, reply="sent text")
    assert calls == ["capture", "settle"]
    assert user_data["_credit_captured_for_turn"] is True


def test_settle_after_failed_send_does_not_capture(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.capture_after_reply_persisted",
        lambda *a, **k: calls.append("capture"),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.on_ai_failed", lambda ctx: calls.append("fail"))
    monkeypatch.setattr("services.ai_reply_turn_runtime.persist_generated_reply", lambda *a, **k: None)
    user_data = {
        "_logical_reply_id": "lid-fail",
        "tenant_id": "shop",
        "_last_outbound_delivery": {"success": False, "retryable": False, "submitted": False},
    }
    settle_after_outbound(user_data, reply="never sent")
    assert calls == ["fail"]
    assert user_data.get("_credit_captured_for_turn") is not True


def test_settle_after_outbound_without_evidence_keeps_hold(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.capture_after_reply_persisted",
        lambda *a, **k: calls.append("capture"),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.on_ai_failed", lambda ctx: calls.append("fail"))
    monkeypatch.setattr("services.ai_reply_turn_runtime.persist_generated_reply", lambda *a, **k: None)
    user_data = {"_logical_reply_id": "lid-no-ev", "tenant_id": "shop"}
    settle_after_outbound(user_data, reply="generated only")
    assert user_data["_reply_ready"] is True
    assert calls == []


def test_settle_after_unknown_send_keeps_hold(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.capture_after_reply_persisted",
        lambda *a, **k: calls.append("capture"),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.on_ai_failed", lambda ctx: calls.append("fail"))
    monkeypatch.setattr("services.ai_reply_turn_runtime.persist_generated_reply", lambda *a, **k: None)
    user_data = {
        "_logical_reply_id": "lid-unk",
        "tenant_id": "shop",
        "_last_outbound_delivery": {"success": False, "retryable": True},
    }
    settle_after_outbound(user_data, reply="maybe sent")
    assert user_data["_reply_ready"] is True
    assert calls == []


def test_settle_without_reply_keeps_ready_hold(monkeypatch) -> None:
    failed: list[str] = []
    monkeypatch.setattr("services.ai_reply_turn_runtime.on_ai_failed", lambda ctx: failed.append("fail"))
    settle_reserved_credits({"_logical_reply_id": "lid-3", "_reply_ready": True}, reply="")
    assert failed == []


def test_finalize_delivery_captures_on_success(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.capture_after_reply_persisted",
        lambda *a, **k: calls.append("capture"),
    )
    monkeypatch.setattr("services.customer_ai.billing.settle_after_send", lambda **k: None)
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.get_turn",
        lambda _lid: type("T", (), {"state": "DELIVERED", "delivery_evidence": {"success": True}, "outbound_state": "sent", "credit_captured": True, "generated_reply": "hi", "logical_reply_id": "lid-4"})(),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.record_delivery_outcome", lambda *a, **k: None)
    monkeypatch.setattr("services.ai_reply_turn_runtime.maybe_record_product_outbound", lambda *a, **k: None)
    user_data = {"_logical_reply_id": "lid-4", "_delivery_succeeded": True, "tenant_id": "shop"}
    summary = finalize_delivery({"user_data": user_data})
    assert "capture" in calls
    assert summary["delivery"] == "delivered"


def test_finalize_delivery_releases_brain_hold_on_never_submitted_fail(monkeypatch) -> None:
    released: list[str] = []
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime._release_unused_hold",
        lambda user_data: released.append(str(user_data.get("_logical_reply_id") or "")),
    )
    monkeypatch.setattr(
        "services.ai_reply_turn_runtime.get_turn",
        lambda _lid: type(
            "T",
            (),
            {
                "state": "PERMANENT_DELIVERY_BLOCK",
                "delivery_evidence": {"success": False, "retryable": False, "submitted": False},
                "outbound_state": "failed",
                "credit_captured": False,
                "generated_reply": "hi",
                "logical_reply_id": "lid-fail",
            },
        )(),
    )
    monkeypatch.setattr("services.ai_reply_turn_runtime.record_delivery_outcome", lambda *a, **k: None)
    summary = finalize_delivery(
        {
            "user_data": {
                "_logical_reply_id": "lid-fail",
                "_last_outbound_delivery": {"success": False, "retryable": False, "submitted": False},
                "tenant_id": "shop",
            }
        }
    )
    assert released == ["lid-fail"]
    assert summary["terminal"] is True


def test_stale_credit_index_marks_unresolved_without_refund() -> None:
    rid = "rid-stale-1"
    record_open(tenant_id="idx-shop", reservation_id=rid, request_id="wa:mid", operation_type="whatsapp")
    from services.membership import credit_reservation_index as index

    index._ITEMS[rid].created_at = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    assert list_stale_open(older_than_seconds=3600)
    assert watch_stale_legacy_credits() == 1
    pending = list_pending()
    assert any(item.reservation_id == rid and item.state == "unresolved" for item in pending)


def test_seed_index_from_known_file_ledger(tmp_path, monkeypatch) -> None:
    import json
    import time

    from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
    from services.membership.credit_reservation_scan import seed_from_known_ledgers

    reset_credit_reservation_index_for_tests()
    ledger = tmp_path / "credit_ledger"
    ledger.mkdir()
    monkeypatch.setattr("services.membership.credit_reservation_scan._DATA_ROOT", tmp_path)
    monkeypatch.setattr("services.membership.credit_reservation_scan.known_credit_tenant_ids", lambda: ["hist-led"])
    rid = "a" * 32
    (ledger / "hist-led.jsonl").write_text(
        json.dumps(
            {
                "id": rid,
                "tenant_id": "hist-led",
                "op": "reserve",
                "credits": 1,
                "request_id": "omni:old",
                "operation_type": "omnichannel_customer_reply",
                "created_at": time.time() - 7200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert seed_from_known_ledgers() == 1
    assert open_counts(tenant_id="hist-led")["open"] == 1


def test_known_tenants_include_memory_settlement_and_index() -> None:
    from services.membership.credit_reservation_index import record_open, reset_credit_reservation_index_for_tests
    from services.membership.credit_reservation_scan import known_credit_tenant_ids
    from services.membership.pending_settlement import reset_pending_settlements_for_tests, upsert

    reset_credit_reservation_index_for_tests()
    reset_pending_settlements_for_tests()
    upsert(
        tenant_id="mem-settle",
        reservation_id="rid-mem-1",
        operation_id="wa:mem",
        billing_policy="legacy_credits",
        state="reserved",
        channel="whatsapp",
    )
    record_open(
        tenant_id="mem-index",
        reservation_id="rid-mem-2",
        request_id="sfu:mem",
        operation_type="smart_followup",
    )
    known = known_credit_tenant_ids()
    assert "mem-settle" in known
    assert "mem-index" in known
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
    from services.customer_ai.outbox import enqueue_envelope, reset_outbox_for_tests

    reset_outbox_for_tests()
    enqueue_envelope(
        tenant_id="mem-outbox",
        operation_id="evt-mem",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Known tenant")],
        ),
    )
    assert "mem-outbox" in known_credit_tenant_ids()


def test_known_credit_tenants_include_pg_reserve_rows(monkeypatch) -> None:
    from contextlib import contextmanager

    from services.membership.credit_reservation_scan import known_credit_tenant_ids

    monkeypatch.setattr("services.billing_backend.billing_uses_postgres", lambda: True)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.billing_backend.require_billing_pg_session", _session)
    monkeypatch.setattr(
        "services.credit_ledger_pg_store.list_reserve_tenant_ids",
        lambda _s: ["pg-reserve"],
    )
    assert "pg-reserve" in known_credit_tenant_ids()


def test_known_tenants_include_jsonl_without_balance(tmp_path, monkeypatch) -> None:
    import json
    import time

    from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
    from services.membership.credit_reservation_scan import known_credit_tenant_ids, seed_from_known_ledgers

    reset_credit_reservation_index_for_tests()
    ledger = tmp_path / "credit_ledger"
    ledger.mkdir()
    monkeypatch.setattr("services.membership.credit_reservation_scan._DATA_ROOT", tmp_path)
    rid = "b" * 32
    (ledger / "jsonl-only.jsonl").write_text(
        json.dumps(
            {
                "id": rid,
                "tenant_id": "jsonl-only",
                "op": "reserve",
                "credits": 1,
                "request_id": "wa:jsonl",
                "operation_type": "whatsapp_customer_reply",
                "created_at": time.time() - 7200,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert "jsonl-only" in known_credit_tenant_ids()
    assert seed_from_known_ledgers() == 1
    assert open_counts(tenant_id="jsonl-only")["open"] == 1


def test_seed_index_from_pending_reserved() -> None:
    from services.membership.credit_reservation_index import (
        _ITEMS,
        open_counts,
        seed_from_pending_settlements,
    )
    from services.membership.pending_settlement import upsert

    upsert(
        tenant_id="hist-shop",
        reservation_id="rid-hist-1",
        operation_id="wa:old",
        billing_policy="legacy_credits",
        state="reserved",
        channel="whatsapp",
        extra={"operation_type": "whatsapp_customer_reply"},
    )
    assert seed_from_pending_settlements() >= 1
    assert open_counts(tenant_id="hist-shop")["open"] == 1
    assert _ITEMS["rid-hist-1"].operation_type == "whatsapp_customer_reply"


def test_open_counts_are_bounded() -> None:
    from services.membership.credit_reservation_index import open_counts

    record_open(tenant_id="idx-shop", reservation_id="rid-open-1", request_id="wa:a", operation_type="whatsapp")
    counts = open_counts(tenant_id="idx-shop")
    assert counts["open"] == 1
    assert counts["stale"] == 0


def test_seed_does_not_reopen_captured_leftover(tmp_path, monkeypatch) -> None:
    import json
    import time

    from services.credit_ledger_pg_store import list_open_leftover_reservations
    from services.membership.credit_reservation_index import open_counts, reset_credit_reservation_index_for_tests
    from services.membership.credit_reservation_scan import leftover_op, seed_from_known_ledgers

    reset_credit_reservation_index_for_tests()
    ledger = tmp_path / "credit_ledger"
    ledger.mkdir()
    monkeypatch.setattr("services.membership.credit_reservation_scan._DATA_ROOT", tmp_path)
    monkeypatch.setattr("services.membership.credit_reservation_scan.known_credit_tenant_ids", lambda: ["cap-led"])
    rid = "c" * 32
    now = time.time() - 7200
    (ledger / "cap-led.jsonl").write_text(
        json.dumps(
            {
                "id": rid,
                "tenant_id": "cap-led",
                "op": "reserve",
                "credits": 1,
                "request_id": "wa:cloud-mid",
                "operation_type": "whatsapp_cloud",
                "created_at": now,
            }
        )
        + "\n"
        + json.dumps(
            {
                "id": "d" * 32,
                "tenant_id": "cap-led",
                "op": "capture",
                "credits": 1,
                "request_id": rid,
                "operation_type": "capture",
                "created_at": now + 1,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    assert leftover_op("whatsapp_cloud")
    assert leftover_op("tiktok")
    assert leftover_op("whatsapp_smart_followup")
    assert "leftover_op" in getsource(list_open_leftover_reservations)
    assert seed_from_known_ledgers() == 0
    assert open_counts(tenant_id="cap-led")["open"] == 0


def test_leftover_index_get_prefers_sql_over_stale_memory(monkeypatch) -> None:
    from contextlib import contextmanager

    from services.membership import credit_reservation_index as index
    from services.membership.credit_reservation_index import OpenCreditReservation, record_open

    item = record_open(
        tenant_id="idx-sql",
        reservation_id="rid-sql-1",
        request_id="wa:sql",
        operation_type="whatsapp",
    )
    assert item is not None
    sql_row = OpenCreditReservation(
        reservation_id=item.reservation_id,
        tenant_id=item.tenant_id,
        request_id=item.request_id,
        operation_type=item.operation_type,
        created_at=item.created_at,
        state="pending_settlement",
    )
    monkeypatch.setattr(index, "_memory_forced", lambda: False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.credit_reservation_index_pg.pg_get", lambda _s, _rid: sql_row)
    found = index._get(item.reservation_id)
    assert found is not None
    assert found.state == "pending_settlement"


def test_list_stale_open_unions_memory_and_sql(monkeypatch) -> None:
    from datetime import datetime, timedelta

    from services.membership import credit_reservation_index as index
    from services.membership.credit_reservation_index import OpenCreditReservation, list_stale_open, record_open

    old = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
    item = record_open(
        tenant_id="idx-stale",
        reservation_id="rid-mem-stale",
        request_id="wa:mem-stale",
        operation_type="whatsapp",
        created_at=old,
    )
    assert item is not None
    sql_row = OpenCreditReservation(
        reservation_id="rid-sql-stale",
        tenant_id="idx-sql-stale",
        request_id="wa:sql-stale",
        operation_type="whatsapp",
        created_at=old,
        state="reserved",
    )
    monkeypatch.setattr(index, "_list_pg", lambda **_k: [sql_row])
    monkeypatch.setattr(index, "_sql_known_ids", lambda **_k: {sql_row.reservation_id})
    rows = list_stale_open(older_than_seconds=3600)
    ids = {row.reservation_id for row in rows}
    assert "rid-mem-stale" in ids
    assert "rid-sql-stale" in ids


def test_open_counts_union_memory_and_sql(monkeypatch) -> None:
    from services.membership import credit_reservation_index as index
    from services.membership.credit_reservation_index import OpenCreditReservation, open_counts, record_open

    record_open(
        tenant_id="idx-open-mem",
        reservation_id="rid-open-mem",
        request_id="wa:open-mem",
        operation_type="whatsapp",
    )
    sql_row = OpenCreditReservation(
        reservation_id="rid-open-sql",
        tenant_id="idx-open-sql",
        request_id="wa:open-sql",
        operation_type="whatsapp",
        created_at="2026-01-01T00:00:00+00:00",
        state="reserved",
    )
    monkeypatch.setattr(index, "_list_pg", lambda **_k: [sql_row])
    monkeypatch.setattr(index, "_sql_known_ids", lambda **_k: {sql_row.reservation_id})
    counts = open_counts()
    assert counts["open"] >= 2


def test_sfu_uses_leftover_reserve() -> None:
    from services.smart_followup.worker_job import process_one_followup_job

    src = getsource(process_one_followup_job)
    assert "reserve_leftover_reply" in src
    assert src.index("if message_billing_enabled()") < src.index("reserve_leftover_reply")
