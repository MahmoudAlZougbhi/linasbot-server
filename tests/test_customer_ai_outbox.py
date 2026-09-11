"""Durable Brain outbox recovers the same envelope without regenerating."""

from __future__ import annotations

from services.customer_ai.billing import apply_message_billing
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.outbox import (
    _ITEMS,
    acknowledge_failed,
    acknowledge_pending_settlement,
    acknowledge_sent,
    enqueue_envelope,
    envelope_from_item,
    mark_failed,
    mark_pending_settlement,
    mark_sent,
    outbox_counts,
    recover_pending_settlement,
    recover_unsent,
    reset_outbox_for_tests,
)


def setup_function() -> None:
    reset_outbox_for_tests()


def test_enqueue_is_idempotent_and_recover_does_not_regenerate() -> None:
    envelope = FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination="dm", text="Hello", idempotency_key="k1")],
    )
    first = enqueue_envelope(tenant_id="shop", operation_id="evt-1", envelope=envelope)
    second = enqueue_envelope(
        tenant_id="shop",
        operation_id="evt-1",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="DIFFERENT", idempotency_key="k1")],
        ),
    )
    assert first.outbox_id == second.outbox_id
    recovered = recover_unsent(tenant_id="shop")
    assert len(recovered) == 1
    assert envelope_from_item(recovered[0]).reply_text == "Hello"
    mark_sent(first.outbox_id, provider_message_id="mid-1")
    assert recover_unsent(tenant_id="shop") == []
    mark_pending_settlement(first.outbox_id)
    pending = recover_pending_settlement(tenant_id="shop")
    assert len(pending) == 1
    assert pending[0].provider_message_id == "mid-1"
    assert envelope_from_item(pending[0]).reply_text == "Hello"


def test_apply_message_billing_persists_accepted_envelope() -> None:
    result = apply_message_billing(
        CustomerTurn(tenant_id="shop", conversation_id="c1", event_ids=["evt-9"], channel="whatsapp"),
        TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="Same text after crash")],
            ),
            extra={"phase": "generate"},
        ),
    )
    recovered = recover_unsent(tenant_id="shop")
    assert len(recovered) == 1
    assert recovered[0].operation_id == result.extra["operation_id"] == "evt-9"
    assert envelope_from_item(recovered[0]).reply_text == "Same text after crash"
    acknowledge_sent(tenant_id="shop", operation_id="evt-9", provider_message_id="wamid-1")
    assert recover_unsent(tenant_id="shop") == []
    acknowledge_pending_settlement(tenant_id="shop", operation_id="evt-9", provider_message_id="wamid-1")
    pending = recover_pending_settlement(tenant_id="shop")
    assert pending[0].provider_message_id == "wamid-1"
    assert envelope_from_item(pending[0]).reply_text == "Same text after crash"
    assert outbox_counts(tenant_id="shop")["pending_settlement"] == 1


def test_outbox_survives_memory_clear(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.delenv("LINAS_BILLING_BACKEND", raising=False)
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    reset_outbox_for_tests()
    enqueue_envelope(
        tenant_id="disk-shop",
        operation_id="evt-disk",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Persisted")],
        ),
        extra={"channel": "instagram_dm"},
    )
    _ITEMS.clear()
    import services.customer_ai.outbox as outbox

    outbox._HYDRATED = False
    recovered = recover_unsent(tenant_id="disk-shop")
    assert len(recovered) == 1
    assert envelope_from_item(recovered[0]).reply_text == "Persisted"
    assert recovered[0].extra["channel"] == "instagram_dm"


def test_failed_send_keeps_envelope_out_of_unsent() -> None:
    envelope = FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination="dm", text="Do not regenerate")],
    )
    enqueue_envelope(tenant_id="fail-shop", operation_id="evt-fail", envelope=envelope)
    acknowledge_failed(tenant_id="fail-shop", operation_id="evt-fail")
    assert recover_unsent(tenant_id="fail-shop") == []
    assert outbox_counts(tenant_id="fail-shop")["failed"] == 1
    again = enqueue_envelope(
        tenant_id="fail-shop",
        operation_id="evt-fail",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="REGENERATED")],
        ),
    )
    assert envelope_from_item(again).reply_text == "Do not regenerate"


def test_mark_failed_does_not_overwrite_sql_sent(monkeypatch) -> None:
    from contextlib import contextmanager
    from dataclasses import replace

    from services.customer_ai import outbox as box

    item = enqueue_envelope(
        tenant_id="sent-shop",
        operation_id="evt-sent",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Already sent")],
        ),
    )
    sql_sent = replace(item, state="sent", provider_message_id="mid-sql")
    monkeypatch.setattr(box, "_memory_forced", lambda: False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.customer_ai.outbox_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_get", lambda _s, _oid: sql_sent)
    marked = mark_failed(item.outbox_id)
    assert marked is not None
    assert marked.state == "sent"
    assert marked.provider_message_id == "mid-sql"


def test_outbox_counts_and_recover_union_memory_and_sql(monkeypatch) -> None:
    from contextlib import contextmanager

    from services.customer_ai.outbox import OutboxItem, known_outbox_tenant_ids

    enqueue_envelope(
        tenant_id="mem-out",
        operation_id="evt-mem",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Memory envelope")],
        ),
    )
    sql_item = OutboxItem(
        outbox_id="sql-out:evt-sql",
        tenant_id="sql-out",
        operation_id="evt-sql",
        reservation_id="evt-sql",
        billing_policy="message_units",
        state="accepted",
        envelope={"decision": "reply", "messages": [{"destination": "dm", "text": "SQL"}]},
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.customer_ai.outbox_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_counts", lambda *_a, **_k: {"accepted": 1, "sent": 0, "pending_settlement": 0, "failed": 0})
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_outbox_ids", lambda *_a, **_k: {sql_item.outbox_id})
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_tenant_ids", lambda *_a, **_k: ["sql-out"])
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_list", lambda *_a, **_k: [sql_item])
    counts = outbox_counts()
    assert counts["accepted"] == 2
    tenants = known_outbox_tenant_ids()
    assert "mem-out" in tenants
    assert "sql-out" in tenants
    recovered = recover_unsent()
    ids = {item.tenant_id for item in recovered}
    assert "mem-out" in ids
    assert "sql-out" in ids


def test_recover_unsent_skips_memory_row_already_known_in_sql(monkeypatch) -> None:
    from contextlib import contextmanager

    from services.customer_ai.outbox import OutboxItem, reset_outbox_for_tests

    reset_outbox_for_tests()
    item = enqueue_envelope(
        tenant_id="stale-out",
        operation_id="evt-stale",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Stale accepted")],
        ),
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.customer_ai.outbox_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_list", lambda *_a, **_k: [])
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_outbox_ids", lambda *_a, **_k: {item.outbox_id})
    assert recover_unsent(tenant_id="stale-out") == []
    sql_open = OutboxItem(
        outbox_id="sql-open:evt-open",
        tenant_id="stale-out",
        operation_id="evt-open",
        reservation_id="evt-open",
        billing_policy="message_units",
        state="accepted",
        envelope={"decision": "reply", "messages": [{"destination": "dm", "text": "SQL open"}]},
    )
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_list", lambda *_a, **_k: [sql_open])
    monkeypatch.setattr(
        "services.customer_ai.outbox_pg.pg_outbox_ids",
        lambda *_a, **_k: {item.outbox_id, sql_open.outbox_id},
    )
    recovered = recover_unsent(tenant_id="stale-out")
    assert [row.outbox_id for row in recovered] == [sql_open.outbox_id]


def test_hydrate_skips_disk_accepted_when_sql_already_has_id(tmp_path, monkeypatch) -> None:
    import json
    from contextlib import contextmanager

    from services.customer_ai import outbox as outbox_mod

    reset_outbox_for_tests()
    folder = tmp_path / "outbox"
    folder.mkdir()
    oid = "disk-out:evt-disk"
    (folder / "disk.json").write_text(
        json.dumps(
            {
                "outbox_id": oid,
                "tenant_id": "disk-out",
                "operation_id": "evt-disk",
                "reservation_id": "evt-disk",
                "billing_policy": "legacy_credits",
                "state": "accepted",
                "envelope": {"decision": "reply", "messages": [{"destination": "dm", "text": "stale"}]},
            }
        ),
        encoding="utf-8",
    )

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr(outbox_mod, "_root", lambda: folder)
    monkeypatch.setattr(outbox_mod, "_memory_forced", lambda: False)
    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.customer_ai.outbox_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_list", lambda *_a, **_k: [])
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_outbox_ids", lambda *_a, **_k: {oid})
    monkeypatch.setattr("services.customer_ai.outbox_pg.pg_get", lambda *_a, **_k: object())
    outbox_mod._ITEMS.clear()
    outbox_mod._HYDRATED = False
    outbox_mod._hydrate()
    assert oid not in outbox_mod._ITEMS
    assert recover_unsent(tenant_id="disk-out") == []
