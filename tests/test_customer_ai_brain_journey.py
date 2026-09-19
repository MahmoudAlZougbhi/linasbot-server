"""Brain journey: Terra tools own requests; no silent media send; FAQ path unchanged."""

from __future__ import annotations

import pytest

from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.tools.registry import execute_tool
from services.brain.turn_pipeline import run_dm_after_gates
from tests.plan_builders import explicit_plan


def _skip_faq(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_confirm(*_a, **_k):
        return None

    async def _no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", _no_confirm)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", _no_sem)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)


async def _found_retrieve(*_a, **_k):
    return (
        EvidenceBundle(
            outcome="found",
            items=[
                EvidenceItem(
                    evidence_id="knowledge:policy",
                    source_family="knowledge",
                    source_id="policy",
                    title="Policy",
                    text="Refunds section",
                )
            ],
        ),
        [],
        {},
    )


async def _fake_generate(turn, **kwargs):
    extra = dict(kwargs.get("extra") or turn.extra or {})
    extra.update(dict(turn.extra or {}))
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Terra reply from evidence.")],
        ),
        extra=extra,
    )


async def _terra_start_turn(turn, **kwargs):
    message = str(kwargs.get("message") or "")
    extra = dict(kwargs.get("extra") or turn.extra or {})
    result = await execute_tool(
        "start_request",
        {"request_type": "APPOINTMENT", "title": message, "task_id": "book", "customer_text": message},
        turn,
    )
    extra["request_state"] = {"module_enabled": True}
    data = result.get("data") if isinstance(result.get("data"), dict) else {}
    if data.get("awaiting_confirmation"):
        extra["awaiting_confirmation"] = True
        extra["pending_actions"] = list(data.get("pending_actions") or [])
        turn.extra = {**dict(turn.extra or {}), **extra}
    extra.update(dict(turn.extra or {}))
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Terra reply from evidence.")],
        ),
        extra=extra,
    )


async def _terra_escalate_turn(turn, **kwargs):
    message = str(kwargs.get("message") or "")
    extra = dict(kwargs.get("extra") or turn.extra or {})
    result = await execute_tool("escalate_to_human", {"task_id": "human", "customer_text": message}, turn)
    extra["request_state"] = {"module_enabled": True}
    extra["receipts"] = []
    if result.get("receipt"):
        extra["receipts"] = [result["receipt"]]
    turn.extra = {**dict(turn.extra or {}), **extra}
    extra.update(dict(turn.extra or {}))
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Terra reply from evidence.")],
        ),
        extra=extra,
    )


@pytest.mark.asyncio
async def test_resource_request_does_not_fake_booking_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    _skip_faq(monkeypatch)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _found_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", _fake_generate)
    turn = CustomerTurn(tenant_id="brain-shop", conversation_id="c1", event_ids=["m1"], channel="instagram_dm")
    result = await run_dm_after_gates(turn, message="send me the before photo please", channel="instagram_dm")
    assert result.extra.get("awaiting_confirmation") is not True
    assert not any(item.get("action_type") == "send_resource" for item in result.extra.get("receipts") or [])
    assert "confirm the details" not in (result.envelope.reply_text or "").lower()


@pytest.mark.asyncio
async def test_booking_still_asks_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    _skip_faq(monkeypatch)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _found_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", _terra_start_turn)
    turn = CustomerTurn(tenant_id="brain-shop", conversation_id="c2", event_ids=["m2"], channel="whatsapp")
    result = await run_dm_after_gates(turn, message="I want to book a laser appointment", channel="whatsapp")
    assert result.extra.get("awaiting_confirmation") is True


def test_scenario_planner_slices_match_contract_intents() -> None:
    cases = [
        ("How much is laser?", (("information", ["services", "prices"]),)),
        ("What are Saturday hours?", (("hours", ["hours", "branches"]),)),
        (
            "How much is laser and what are the hours?",
            (("information", ["services", "prices"]), ("hours", ["hours", "branches"])),
        ),
        ("send the product photo", (("resource_request", ["products"]),)),
        (
            "I want to book and talk to a human",
            (("service_request", ["services"]), ("human_request", ["none"])),
        ),
    ]
    for message, typed in cases:
        types = {task.type for task in explicit_plan(message, *typed).tasks}
        expected = {item[0] for item in typed}
        assert expected <= types, (message, types)


@pytest.mark.asyncio
async def test_handoff_executes_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    _skip_faq(monkeypatch)

    async def fake_escalate(**_k):
        from services.brain.contracts.actions import ActionReceipt

        return ActionReceipt(action_id="handoff:t_human", action_type="escalate_to_human", state="success")

    monkeypatch.setattr("services.brain.actions.execute.escalate_to_human", fake_escalate)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _found_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", _terra_escalate_turn)
    turn = CustomerTurn(tenant_id="brain-shop", customer_id="u1", conversation_id="c3", event_ids=["m3"])
    result = await run_dm_after_gates(turn, message="I want a human please", channel="instagram_dm")
    receipts = list(result.extra.get("receipts") or [])
    assert any(item.get("action_type") == "escalate_to_human" and item.get("state") == "success" for item in receipts)


def test_deep_knowledge_chunk_is_indexed_separately() -> None:
    from services.brain.retrieve.cards import TitleCard
    from services.brain.search.index_job import document_rows

    card = TitleCard(
        item_id="knowledge:doc",
        source_family="knowledge",
        title="Policy",
        search_text="Policy",
        body="# Intro\nWelcome.\n# Deep Policy\nOnly this later section mentions copper cooling gel.\n",
        revision="v1",
        chunks=("Welcome.", "Only this later section mentions copper cooling gel."),
    )
    rows = document_rows([card], tenant_id="brain-shop", version="v1")
    assert len(rows) == 2
    assert any("copper cooling gel" in row["search_text"] for row in rows)
    assert {row["chunk_id"] for row in rows} == {"knowledge:doc:c1", "knowledge:doc:c2"}
