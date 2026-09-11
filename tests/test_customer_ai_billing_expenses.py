"""Customer Brain billing class + provider expenses. Activation flags stay off."""

from __future__ import annotations

import pytest

from services.customer_ai.billing import apply_message_billing, classify_result
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.outbox import reset_outbox_for_tests
from services.membership.expense_journal import list_events, reset_expenses_for_tests
from services.membership.message_ledger import reset_ledger_for_tests


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    reset_ledger_for_tests()
    reset_expenses_for_tests()
    reset_outbox_for_tests()


def _turn(**kwargs) -> CustomerTurn:
    values = {
        "tenant_id": "bill-shop",
        "conversation_id": "c1",
        "event_ids": ["evt-1"],
    }
    values.update(kwargs)
    return CustomerTurn(**values)


def test_classify_semantic_faq_is_zero_unit() -> None:
    result = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="deterministic",
            messages=[OutboundMessage(destination="dm", text="Hours are 9-5.")],
        ),
        extra={"path": "faq_semantic", "faq_id": "hours"},
    )
    assert classify_result(_turn(), result) == "faq_only"


def test_classify_mixed_faq_ai_before_generated() -> None:
    result = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="The facial is $40.")],
        ),
        ai_called=True,
        extra={"faq_id": "price-1", "faq_used": True, "phase": "generate"},
    )
    assert classify_result(_turn(), result) == "mixed_faq_ai"


def test_expenses_record_when_billing_is_off() -> None:
    result = apply_message_billing(
        _turn(),
        TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="Hello")],
            ),
            ai_called=True,
            extra={"phase": "generate"},
        ),
    )
    assert result.extra["response_class"] == "generated_ai"
    assert result.extra["message_units"] == 1
    events = list_events(tenant_id="bill-shop")
    assert events
    assert events[0].category == "llm_generation"
    assert events[0].status == "pending"
    assert events[0].amount_usd is None


def test_faq_only_does_not_open_a_lot_when_billing_off() -> None:
    from services.membership.message_ledger import remaining_messages

    apply_message_billing(
        _turn(),
        TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="deterministic",
                messages=[OutboundMessage(destination="dm", text="Yes")],
            ),
            extra={"path": "faq_exact", "faq_id": "q1"},
        ),
    )
    assert remaining_messages("bill-shop") == 0


def test_index_embed_records_pending_voyage(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from services.customer_ai.search.index_job import index_published_tenant
    from services.membership.processing_budgets import reset_processing_budgets_for_tests

    reset_processing_budgets_for_tests()
    monkeypatch.setattr("services.customer_ai.search.index_job.voyage_configured", lambda: True)
    monkeypatch.setattr(
        "services.customer_ai.search.index_job.load_published_cards",
        lambda _tid: [],
    )
    monkeypatch.setattr("services.customer_ai.search.index_job.load_product_cards", lambda _tid: [])
    monkeypatch.setattr(
        "services.customer_ai.search.index_job.embed_document_rows",
        lambda _rows: asyncio.sleep(0, result=[]),
    )

    async def _run() -> None:
        await index_published_tenant("idx-shop", revision="v-test")

    asyncio.run(_run())
    events = list_events(tenant_id="idx-shop", category="embedding")
    assert events
    assert events[0].provider == "voyage"
    assert events[0].status == "pending"
