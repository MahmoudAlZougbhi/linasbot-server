"""Owner message-flow inspector reads durable outbox timelines."""

from __future__ import annotations

from services.customer_ai.billing import apply_message_billing
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn, HistorySnapshot, VisibleMessage
from services.customer_ai.outbox import reset_outbox_for_tests
from services.customer_ai.turn_inspector import get_message_flow, list_message_flows
from services.membership.expense_journal import reset_expenses_for_tests
from services.membership.message_ledger import reset_ledger_for_tests


def setup_function() -> None:
    reset_outbox_for_tests()
    reset_expenses_for_tests()
    reset_ledger_for_tests()


def test_message_flow_exposes_human_stages_and_cost() -> None:
    turn = CustomerTurn(
        tenant_id="flow-shop",
        conversation_id="c1",
        channel="instagram_dm",
        event_ids=["mid-flow-1"],
        history=HistorySnapshot(
            messages=[VisibleMessage(id="mid-flow-1", role="user", text="How much is laser?", is_current_inbound=True)]
        ),
    )
    result = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Laser starts at published price.")],
            used_evidence_ids=["knowledge:laser"],
        ),
        ai_called=True,
        extra={
            "phase": "generate",
            "stage_timeline": [
                {
                    "stage": "search",
                    "title": "Searched published Knowledge",
                    "at": "2026-09-11T00:00:00+00:00",
                    "detail": {
                        "ms": 12,
                        "evidence": [{"id": "knowledge:laser", "family": "knowledge", "title": "Laser", "preview": "price"}],
                    },
                }
            ],
            "evidence_preview": [{"id": "knowledge:laser", "family": "knowledge", "title": "Laser", "preview": "price"}],
        },
    )
    billed = apply_message_billing(turn, result)
    assert billed.extra.get("stage_timeline")
    rows = list_message_flows(tenant_id="flow-shop", limit=10)
    assert rows
    assert rows[0]["operation_id"] == "mid-flow-1"
    detail = get_message_flow(tenant_id="flow-shop", operation_id="mid-flow-1")
    assert detail is not None
    assert detail["inbound_preview"].startswith("How much")
    assert any(stage["stage"] == "search" for stage in detail["flow"])
    assert detail["evidence_sent_to_ai"]
    assert detail["cost"]["pending_events"] >= 1
