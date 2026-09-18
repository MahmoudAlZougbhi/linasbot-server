"""Long Meta provider IDs persist without truncation; outbox failure stays silent."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

from db.models import Base
from db.models.id_lengths import COMPOSITE_REF_MAX, PROVIDER_REF_MAX
from db.session import reset_engine_for_tests
from services.billing.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests
from services.billing.membership.pending_settlement import reset_pending_settlements_for_tests
from services.brain.billing import apply_message_billing, operation_id_for_turn
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.outbox import (
    OutboxPersistError,
    enqueue_envelope,
    envelope_from_item,
    outbox_id_for,
    recover_unsent,
    reset_outbox_for_tests,
)
from services.brain.outbox_turn import persist_turn_result
from services.brain.turn_pipeline import inbound_task_text


def _mid(n: int) -> str:
    return "m" * n


@pytest.fixture()
def sql_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'provider_ids.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "postgres")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    reset_engine_for_tests()
    reset_ledger_for_tests()
    reset_pending_settlements_for_tests()
    reset_outbox_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()
    reset_ledger_for_tests()
    reset_outbox_for_tests()


@pytest.mark.parametrize("n", [164, 200, 512])
def test_long_meta_id_persists_without_truncation(sql_store: Path, n: int) -> None:
    mid = _mid(n)
    assert n <= PROVIDER_REF_MAX
    tenant = "linas"
    oid = outbox_id_for(tenant, mid)
    assert len(oid) <= COMPOSITE_REF_MAX
    envelope = FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination="dm", text="We open at 10.")],
    )
    item = enqueue_envelope(tenant_id=tenant, operation_id=mid, envelope=envelope, reservation_id=mid)
    assert item.operation_id == mid
    assert item.outbox_id == oid
    from db.session import whatsapp_session

    with whatsapp_session(require=True) as session:
        row = session.execute(
            text("SELECT operation_id, outbox_id FROM customer_ai_outbox WHERE outbox_id = :oid"),
            {"oid": oid},
        ).first()
    assert row is not None
    assert row[0] == mid
    assert row[1] == oid
    again = enqueue_envelope(
        tenant_id=tenant,
        operation_id=mid,
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="DUPLICATE")],
        ),
    )
    assert envelope_from_item(again).reply_text == "We open at 10."
    recovered = recover_unsent(tenant_id=tenant)
    assert [row.operation_id for row in recovered] == [mid]


def test_duplicate_webhook_one_outbox_row(sql_store: Path) -> None:
    mid = _mid(164)
    turn = CustomerTurn(tenant_id="linas", conversation_id="c1", event_ids=[mid], channel="instagram_dm")
    result = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Hello from Terra")],
        ),
        extra={"operation_id": operation_id_for_turn(turn), "phase": "generate"},
        ai_called=True,
    )
    first = persist_turn_result(turn, result)
    second = persist_turn_result(turn, result)
    assert first is not None and second is not None
    assert first.outbox_id == second.outbox_id
    assert len(recover_unsent(tenant_id="linas")) == 1


def test_outbox_failure_silences_and_does_not_keep_memory_row(sql_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr("services.brain.outbox._persist", boom)
    envelope = FinalReplyEnvelope(
        decision="reply",
        messages=[OutboundMessage(destination="dm", text="should not send")],
    )
    with pytest.raises(OutboxPersistError):
        enqueue_envelope(tenant_id="linas", operation_id=_mid(164), envelope=envelope)
    assert recover_unsent(tenant_id="linas") == []


def test_apply_billing_outbox_failure_is_failed_closed(sql_store: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.brain.outbox._persist",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("pg down")),
    )
    turn = CustomerTurn(tenant_id="linas", conversation_id="c1", event_ids=[_mid(164)], channel="instagram_dm")
    out = apply_message_billing(
        turn,
        TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="internal should not leak")],
            ),
            extra={"phase": "generate"},
            ai_called=True,
        ),
    )
    assert out.stop_reason == "failed_closed"
    assert not out.envelope.messages
    assert out.extra.get("customer_silence") is True
    assert recover_unsent(tenant_id="linas") == []


def test_hello_stays_terra_path_not_catalog() -> None:
    turn = CustomerTurn(tenant_id="linas", conversation_id="c1", surface="dm")
    assert inbound_task_text(turn, "Hello") == "Hello"


def test_ledger_long_operation_id(sql_store: Path) -> None:
    from services.billing.membership.lot_window import current_period_id
    from services.billing.membership.message_ledger import reserve, settle

    mid = _mid(164)
    grant_lot(
        tenant_id="linas",
        lot_id="inc",
        kind="included",
        period_id=current_period_id(),
        amount=5,
    )
    reserve(tenant_id="linas", operation_id=mid, response_class="generated_ai")
    settle(tenant_id="linas", operation_id=mid, accepted=False)
    assert remaining_messages("linas") == 5
