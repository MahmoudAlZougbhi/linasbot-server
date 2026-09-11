"""Durable SQL path for message ledger, daily edits, and expenses.

Uses sqlite through the billing session, the same adapters as Postgres.
Does not enable activation flags or convert credits.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.membership.daily_edits import commit_edit, reserve_edit, reset_daily_edits_for_tests, status
from services.membership.expense_journal import list_events, record_expense, reset_expenses_for_tests
from services.membership.lot_window import current_period_id
from services.membership.message_ledger import (
    grant_lot,
    grant_purchased,
    remaining_messages,
    reserve,
    reset_ledger_for_tests,
    revoke_purchased,
    settle,
)
from services.membership.pending_settlement import (
    list_pending,
    record_pending_after_send,
    reset_pending_settlements_for_tests,
)
from services.membership.pg_store import store_backend
from services.membership.reconcile import ledger_health


@pytest.fixture()
def sql_message_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'message_billing.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "postgres")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    reset_engine_for_tests()
    reset_ledger_for_tests()
    reset_daily_edits_for_tests()
    reset_expenses_for_tests()
    reset_pending_settlements_for_tests()
    from services.customer_ai.conversation_store import reset_conversation_store_for_tests
    from services.customer_ai.outbox import reset_outbox_for_tests
    from services.membership.catalog_admin import reset_catalog_admin_for_tests
    from services.membership.credit_reservation_index import reset_credit_reservation_index_for_tests
    from services.membership.processing_budgets import reset_processing_budgets_for_tests

    reset_outbox_for_tests()
    reset_conversation_store_for_tests()
    reset_catalog_admin_for_tests()
    reset_credit_reservation_index_for_tests()
    reset_processing_budgets_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()
    reset_ledger_for_tests()
    reset_daily_edits_for_tests()
    reset_expenses_for_tests()


def test_sql_ledger_grant_reserve_settle(sql_message_store: Path) -> None:
    assert store_backend() == "postgres"
    grant_lot(
        tenant_id="sql-shop",
        lot_id="sql-inc",
        kind="included",
        period_id=current_period_id(),
        amount=5,
    )
    assert remaining_messages("sql-shop") == 5
    reserve(tenant_id="sql-shop", operation_id="gen-1", response_class="generated_ai")
    settle(tenant_id="sql-shop", operation_id="gen-1", accepted=True)
    assert remaining_messages("sql-shop") == 4
    health = ledger_health("sql-shop")
    assert health["ok"] is True
    assert health["store"] == "postgres"
    assert health["remaining"] == 4


def test_sql_ledger_zero_debit_does_not_spend(sql_message_store: Path) -> None:
    grant_lot(
        tenant_id="sql-faq",
        lot_id="sql-faq-inc",
        kind="included",
        period_id=current_period_id(),
        amount=3,
    )
    reserve(tenant_id="sql-faq", operation_id="faq-1", response_class="faq_only")
    settle(tenant_id="sql-faq", operation_id="faq-1", accepted=True)
    assert remaining_messages("sql-faq") == 3


def test_sql_daily_edits_and_expenses(sql_message_store: Path) -> None:
    first = reserve_edit(tenant_id="sql-edit", operation_id="op-1")
    assert first.allow is True
    commit_edit(tenant_id="sql-edit", operation_id="op-1")
    state = status("sql-edit")
    assert state.used == 1
    assert state.remaining == state.limit - 1
    record_expense(
        event_id="exp-1",
        tenant_id="sql-edit",
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model="answer",
        amount_usd=None,
        status="pending",
        operation_id="op-1",
    )
    events = list_events(tenant_id="sql-edit")
    assert len(events) == 1
    assert events[0].status == "pending"
    assert events[0].amount_usd is None


def test_sql_revoke_purchased_lot(sql_message_store: Path) -> None:
    grant_purchased(
        tenant_id="sql-rev",
        lot_id="sql-rev:messages_100:txn-sql",
        amount=40,
        source_transaction_id="txn-sql",
    )
    reserve(tenant_id="sql-rev", operation_id="hold-sql", response_class="generated_ai")
    assert remaining_messages("sql-rev") == 39
    result = revoke_purchased(tenant_id="sql-rev", transaction_id="txn-sql")
    assert result["revoked"] is True
    assert result["remaining_cleared"] == 40
    assert result["reservations_released"] == 1
    assert remaining_messages("sql-rev") == 0


def test_sql_pending_settlement_survives_memory_clear(sql_message_store: Path) -> None:
    record_pending_after_send(
        tenant_id="sql-hold",
        reservation_id="rid-sql",
        operation_id="op-sql",
        billing_policy="legacy_credits",
        provider_message_id="wamid-sql",
        channel="whatsapp",
    )
    from services.membership.pending_settlement import _ITEMS

    _ITEMS.clear()
    rows = list_pending(states=("pending_settlement",), tenant_id="sql-hold")
    assert len(rows) == 1
    assert rows[0].send_status == "sent"
    assert rows[0].provider_message_id == "wamid-sql"
    assert rows[0].billing_policy == "legacy_credits"


def test_sql_outbox_survives_memory_clear(sql_message_store: Path) -> None:
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
    from services.customer_ai.outbox import (
        _ITEMS,
        enqueue_envelope,
        envelope_from_item,
        mark_sent,
        recover_unsent,
        reset_outbox_for_tests,
    )

    reset_outbox_for_tests()
    item = enqueue_envelope(
        tenant_id="sql-outbox",
        operation_id="evt-sql",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Same envelope after restart")],
        ),
        extra={"channel": "whatsapp"},
    )
    from services.customer_ai import outbox as outbox_mod

    _ITEMS.clear()
    outbox_mod._HYDRATED = False
    outbox_mod._hydrate()
    assert "sql-outbox:evt-sql" in outbox_mod._ITEMS
    _ITEMS.clear()
    recovered = recover_unsent(tenant_id="sql-outbox")
    assert len(recovered) == 1
    assert envelope_from_item(recovered[0]).reply_text == "Same envelope after restart"
    assert recovered[0].extra["channel"] == "whatsapp"
    again = enqueue_envelope(
        tenant_id="sql-outbox",
        operation_id="evt-sql",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="REGENERATED")],
        ),
    )
    assert envelope_from_item(again).reply_text == "Same envelope after restart"
    mark_sent(item.outbox_id, provider_message_id="wamid-sql")
    _ITEMS.clear()
    assert recover_unsent(tenant_id="sql-outbox") == []


def test_sql_outbox_promotes_disk_when_pg_row_missing(sql_message_store: Path) -> None:
    from sqlalchemy import text

    import services.customer_ai.outbox as outbox
    from db.session import whatsapp_session
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
    from services.customer_ai.outbox import (
        _ITEMS,
        enqueue_envelope,
        envelope_from_item,
        recover_unsent,
        reset_outbox_for_tests,
    )

    reset_outbox_for_tests()
    enqueue_envelope(
        tenant_id="sql-disk",
        operation_id="evt-disk",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Promoted from disk")],
        ),
    )
    with whatsapp_session(require=True) as session:
        session.execute(text("DELETE FROM customer_ai_outbox"))
    _ITEMS.clear()
    outbox._HYDRATED = False
    recovered = recover_unsent(tenant_id="sql-disk")
    assert len(recovered) == 1
    assert envelope_from_item(recovered[0]).reply_text == "Promoted from disk"


def test_sql_outbox_conflict_keeps_original_envelope(sql_message_store: Path) -> None:
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
    from services.customer_ai.outbox import (
        OutboxItem,
        enqueue_envelope,
        envelope_from_item,
        outbox_id_for,
        recover_unsent,
        reset_outbox_for_tests,
    )
    from services.customer_ai.outbox_pg import pg_upsert, table_ready
    from services.membership.pg_store import optional_message_session

    reset_outbox_for_tests()
    enqueue_envelope(
        tenant_id="sql-keep",
        operation_id="evt-keep",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Original envelope")],
        ),
    )
    with optional_message_session() as session:
        assert session is not None
        assert table_ready(session)
        pg_upsert(
            session,
            OutboxItem(
                outbox_id=outbox_id_for("sql-keep", "evt-keep"),
                tenant_id="sql-keep",
                operation_id="evt-keep",
                reservation_id="evt-keep",
                billing_policy="legacy_credits",
                state="accepted",
                envelope={"decision": "reply", "messages": [{"destination": "dm", "text": "REGENERATED"}]},
            ),
        )
    recovered = recover_unsent(tenant_id="sql-keep")
    assert envelope_from_item(recovered[0]).reply_text == "Original envelope"


def test_sql_settlement_policy_survives_memory_clear(sql_message_store: Path) -> None:
    from services.customer_ai.leftover_reserve import leftover_policy_for
    from services.membership.pending_settlement import (
        _ITEMS,
        get_pending,
        known_settlement_tenant_ids,
        record_hold,
        reset_pending_settlements_for_tests,
    )

    reset_pending_settlements_for_tests()
    record_hold(
        tenant_id="sql-pin",
        reservation_id="rid-pin",
        operation_id="mid-pin",
        billing_policy="legacy_credits",
        extra={"candidate_ids": ["mid-pin", "conv-pin"]},
    )
    _ITEMS.clear()
    assert leftover_policy_for("sql-pin", "mid-pin") == "legacy_credits"
    assert leftover_policy_for("sql-pin", "conv-pin") == "legacy_credits"
    assert get_pending("sql-pin", "rid-pin", "mid-pin") is not None
    assert "sql-pin" in known_settlement_tenant_ids()
    from services.membership.pending_settlement import upsert

    upsert(
        tenant_id="sql-pin",
        reservation_id="rid-pin",
        operation_id="mid-pin",
        billing_policy="legacy_credits",
        state="released",
        reason="unused_or_failed_before_send",
    )
    _ITEMS.clear()
    assert leftover_policy_for("sql-pin", "mid-pin") is None
    assert leftover_policy_for("sql-pin", "conv-pin") is None


def test_sql_settlement_hydrate_loads_pg_rows(sql_message_store: Path) -> None:
    from services.membership import pending_settlement as pending
    from services.membership.pending_settlement import record_hold, reset_pending_settlements_for_tests

    reset_pending_settlements_for_tests()
    record_hold(
        tenant_id="sql-hyd",
        reservation_id="rid-hyd",
        operation_id="mid-hyd",
        billing_policy="legacy_credits",
        extra={"candidate_ids": ["mid-hyd", "conv-hyd"]},
    )
    pending._ITEMS.clear()
    pending._HYDRATED = False
    pending._hydrate()
    held = pending._ITEMS.get("sql-hyd:rid-hyd")
    assert held is not None
    assert "conv-hyd" in (held.extra.get("candidate_ids") or [])


def test_sql_conversation_survives_memory_clear(sql_message_store: Path) -> None:
    from services.customer_ai.contracts.turn import ConversationState
    from services.customer_ai.conversation_store import (
        _MEMORY,
        load_conversation,
        reset_conversation_store_for_tests,
        save_conversation,
    )

    reset_conversation_store_for_tests()
    save_conversation(
        "sql-conv",
        "web:sql-conv:visitor1",
        ConversationState(greeted=True),
        [{"task_id": "book", "kind": "request"}],
        history=[{"id": "m1", "role": "user", "text": "yes"}],
    )
    _MEMORY.clear()
    raw = load_conversation("sql-conv", "web:sql-conv:visitor1")
    assert raw is not None
    assert raw["state"]["greeted"] is True
    assert raw["pending"][0]["task_id"] == "book"
    assert raw["history"][0]["text"] == "yes"
    from services.customer_ai.conversation_store import known_conversation_tenant_ids
    from services.membership.cost_dashboard import global_dashboard

    _MEMORY.clear()
    assert "sql-conv" in known_conversation_tenant_ids()
    tenants = {row["tenant_id"] for row in global_dashboard()["daily_edits"]["tenants"]}
    assert "sql-conv" in tenants


def test_sql_catalog_survives_memory_clear(sql_message_store: Path) -> None:
    from services.membership import catalog_admin as admin
    from services.membership.catalog_admin import current_catalog, reset_catalog_admin_for_tests, update_draft

    reset_catalog_admin_for_tests()
    update_draft(
        actor="owner",
        changes={"plans": {"lite": {"included_messages": 611}}},
        reason="sql",
    )
    admin._DRAFT.clear()
    admin._REVISION = 1
    admin._PUBLISHED = False
    admin._LOADED = True
    restored = current_catalog()
    lite = next(plan for plan in restored["plans"] if plan["plan_id"] == "lite")
    assert lite["included_messages"] == 611
    assert restored["published"] is False


def test_sql_leftover_index_survives_memory_clear(sql_message_store: Path) -> None:
    from services.membership.credit_reservation_index import (
        _ITEMS,
        known_index_tenant_ids,
        mark_closed,
        open_counts,
        record_open,
        reset_credit_reservation_index_for_tests,
    )

    reset_credit_reservation_index_for_tests()
    record_open(
        tenant_id="sql-idx",
        reservation_id="rid-sql-idx",
        request_id="wa:sql-idx",
        operation_type="whatsapp_customer_reply",
    )
    from services.membership import credit_reservation_index as index_mod

    _ITEMS.clear()
    index_mod._HYDRATED = False
    index_mod._hydrate()
    assert "rid-sql-idx" in index_mod._ITEMS
    _ITEMS.clear()
    assert "sql-idx" in known_index_tenant_ids()
    assert open_counts(tenant_id="sql-idx")["open"] == 1
    mark_closed("rid-sql-idx")
    _ITEMS.clear()
    assert open_counts(tenant_id="sql-idx")["open"] == 0


def test_sql_processing_budgets_survive_memory_clear(sql_message_store: Path) -> None:
    from services.membership.processing_budgets import (
        _ATTEMPTS,
        _CONCURRENT,
        _JOBS,
        ProcessingBudgetError,
        begin_job,
        consume_attempt,
        end_job,
        reset_processing_budgets_for_tests,
        status,
    )

    reset_processing_budgets_for_tests()
    consume_attempt("sql-budget", limit=2)
    begin_job("sql-budget")
    _ATTEMPTS.clear()
    _CONCURRENT.clear()
    _JOBS.clear()
    snap = status("sql-budget")
    assert snap["daily_attempts"] == 1
    assert snap["concurrent"] == 1
    consume_attempt("sql-budget", limit=2)
    with pytest.raises(ProcessingBudgetError, match="PROCESSING_DAILY_ATTEMPTS"):
        consume_attempt("sql-budget", limit=2)
    begin_job("sql-budget")
    with pytest.raises(ProcessingBudgetError, match="PROCESSING_CONCURRENCY"):
        begin_job("sql-budget")
    end_job("sql-budget")
    end_job("sql-budget")
    assert status("sql-budget")["concurrent"] == 1


def test_sql_durable_tables_ready_without_enabling(sql_message_store: Path) -> None:
    from services.membership.activation_readiness import activation_readiness
    from services.membership.durable_tables import DURABLE_TABLES, durable_table_report

    report = durable_table_report()
    assert report["ready"] is True
    assert report["store"] == "postgres"
    assert set(report["tables"]) == set(DURABLE_TABLES)
    assert all(report["tables"].values())
    readiness = activation_readiness()
    assert readiness["ready_to_enable"] is False
    assert "durable_tables_incomplete" not in readiness["blockers"]
    assert readiness["durable_tables"]["ready"] is True
