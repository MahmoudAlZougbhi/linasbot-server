"""Brain journey: resource path wiring + isolated scenario slices (mocked providers)."""

from __future__ import annotations

import pytest

from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.turn_pipeline import run_dm_after_gates


@pytest.mark.asyncio
async def test_resource_request_does_not_fake_booking_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_message("send me the before photo please")
    assert any(task.type == "resource_request" for task in plan.tasks)
    assert plan.read_only is False

    async def fake_plan(_message, _history, **_kwargs):
        return plan

    async def fake_retrieve(ctx):
        return EvidenceBundle(
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
        )

    monkeypatch.setattr("services.customer_ai.turn_pipeline.plan_turn", fake_plan)
    monkeypatch.setattr("services.customer_ai.turn_pipeline.retrieve_published", fake_retrieve)
    monkeypatch.setattr(
        "services.cm.setup_resources.index_published_resources",
        lambda _tid: {
            "res_before": {
                "resource_ref": "res_before",
                "title": "Before photo",
                "description": "before treatment photo",
                "resource_type": "image",
                "source_item_id": "knowledge:policy",
            }
        },
    )
    monkeypatch.setattr(
        "services.customer_ai.actions.resources.resolve_published_resource",
        lambda **_k: {
            "ok": True,
            "resource": {"resource_ref": "res_before", "title": "Before photo"},
        },
    )
    async def _no_confirm(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline.try_confirm_pending", _no_confirm)
    monkeypatch.setattr("services.customer_ai.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def _no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline._semantic_faq_result", _no_sem)

    turn = CustomerTurn(tenant_id="brain-shop", conversation_id="c1", event_ids=["m1"], channel="instagram_dm")
    result = await run_dm_after_gates(turn, message="send me the before photo please", channel="instagram_dm")
    assert result.extra.get("phase") == "resource"
    assert result.extra.get("awaiting_confirmation") is not True
    assert result.envelope.decision == "deterministic"
    assert any(item.get("action_type") == "send_resource" for item in result.extra.get("receipts") or [])
    assert "confirm the details" not in (result.envelope.reply_text or "").lower()


@pytest.mark.asyncio
async def test_booking_still_asks_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = plan_message("I want to book a laser appointment")
    assert any(task.type == "service_request" for task in plan.tasks)

    async def fake_plan(_message, _history, **_kwargs):
        return plan

    async def _no_confirm(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline.plan_turn", fake_plan)
    monkeypatch.setattr("services.customer_ai.turn_pipeline.try_confirm_pending", _no_confirm)
    monkeypatch.setattr("services.customer_ai.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def _no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline._semantic_faq_result", _no_sem)
    turn = CustomerTurn(tenant_id="brain-shop", conversation_id="c2", event_ids=["m2"], channel="whatsapp")
    result = await run_dm_after_gates(turn, message="I want to book a laser appointment", channel="whatsapp")
    assert result.extra.get("phase") == "actions_pending"
    assert result.extra.get("awaiting_confirmation") is True


def test_scenario_planner_slices_match_contract_intents() -> None:
    cases = [
        ("How much is laser?", {"information"}),
        ("What are Saturday hours?", {"hours"}),
        ("How much is laser and what are the hours?", {"information", "hours"}),
        ("how much is the first one?", {"information"}),
        ("What is the price? What are the hours? I meant facial not laser", {"information", "draft_correction"}),
        ("send the product photo", {"resource_request"}),
        ("I want to book and talk to a human", {"service_request", "human_request"}),
    ]
    for message, expected in cases:
        types = {task.type for task in plan_message(message).tasks}
        assert expected <= types, (message, types)


@pytest.mark.asyncio
async def test_handoff_executes_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = PlannerPlan(
        tasks=[PlannerTask(id="t_human", type="human_request", span=TaskSpan(text="human"), source_families=["none"])],
        read_only=False,
    )

    async def fake_plan(_message, _history, **_kwargs):
        return plan

    async def fake_escalate(**_k):
        from services.customer_ai.contracts.actions import ActionReceipt

        return ActionReceipt(action_id="handoff:t_human", action_type="escalate_to_human", state="success")

    async def _no_confirm(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline.plan_turn", fake_plan)
    monkeypatch.setattr("services.customer_ai.turn_pipeline.try_confirm_pending", _no_confirm)
    monkeypatch.setattr("services.customer_ai.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def _no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline._semantic_faq_result", _no_sem)
    monkeypatch.setattr("services.customer_ai.actions.execute.escalate_to_human", fake_escalate)
    turn = CustomerTurn(tenant_id="brain-shop", customer_id="u1", conversation_id="c3", event_ids=["m3"])
    result = await run_dm_after_gates(turn, message="I want a human please", channel="instagram_dm")
    assert result.extra.get("phase") == "handoff"
    assert result.envelope.decision == "handoff_ack"
    assert any(item.get("state") == "success" for item in result.extra.get("receipts") or [])


def test_deep_knowledge_chunk_is_indexed_separately() -> None:
    from services.customer_ai.compiler.chunks import chunk_document
    from services.customer_ai.retrieve.cards import TitleCard
    from services.customer_ai.search.index_job import document_rows

    body = "# Intro\nWelcome.\n# Deep Policy\nOnly this later section mentions copper cooling gel.\n"
    chunks = chunk_document(document_id="knowledge:doc", body=body)
    assert any("copper cooling gel" in chunk.text for chunk in chunks)
    assert any("copper cooling gel" not in chunk.text for chunk in chunks)
    card = TitleCard(
        item_id="knowledge:doc",
        source_family="knowledge",
        title="Policy",
        search_text="Policy",
        body=body,
        revision="v1",
    )
    rows = document_rows([card], tenant_id="brain-shop", version="v1")
    assert len(rows) >= 2
    assert any("copper cooling gel" in row["search_text"] for row in rows)
