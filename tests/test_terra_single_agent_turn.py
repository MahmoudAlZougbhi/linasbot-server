"""Freeze: one Terra agent session per customer inbound. No multi-call split."""

from __future__ import annotations

from inspect import getsource
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services.brain.agent import loop as agent_loop
from services.brain.agent.terra_tools import openai_customer_tools
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.turn_pipeline import run_dm_after_gates

ROOT = Path(__file__).resolve().parents[1]
_LOOP = (ROOT / "services/brain/agent/loop.py").read_text(encoding="utf-8")
_GREET = (ROOT / "services/brain/agent/greeting_turn.py").read_text(encoding="utf-8")
_DECIDE = (ROOT / "services/brain/agent/tool_decide.py").read_text(encoding="utf-8")


def test_loop_source_is_single_terra_session() -> None:
    for needle in (
        "plan_turn",
        "openai_plan",
        "run_terra_request_round",
        "propose_tools_dynamic",
        "identity_greeting_result",
        "generate_verified",
        "_maybe_tool_calls",
        "TERRA_SINGLE",
    ):
        assert needle not in _LOOP, needle
    assert "run_terra_turn" in _LOOP
    assert "default_agentic_plan" in getsource(agent_loop.run_agentic_dm_path)


def test_dead_llm_paths_have_no_create_chat_completion() -> None:
    assert "create_chat_completion" not in _GREET
    assert "create_chat_completion" not in _DECIDE
    assert "Pick up to 2 tools" not in _DECIDE


def test_customer_tools_include_request_and_reads() -> None:
    names = {row["function"]["name"] for row in openai_customer_tools()}
    for name in ("start_request", "escalate_to_human", "get_price", "check_setup_resources", "send_resource"):
        assert name in names


def _bundle() -> EvidenceBundle:
    return EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id="k1",
                source_family="knowledge",
                source_id="k1",
                title="Info",
                text="Published fact.",
            )
        ],
    )


async def _found_retrieve(*_a: Any, **_k: Any):
    return _bundle(), [], {}


def _completion(*, content: str = "", name: str = "", arguments: str = "{}"):
    tool_calls = None
    if name:
        tool_calls = [
            SimpleNamespace(id="call_1", function=SimpleNamespace(name=name, arguments=arguments)),
        ]
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))])


@pytest.mark.asyncio
async def test_agentic_dm_does_not_call_plan_or_request_round(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"plan": 0}

    async def boom(*_a: Any, **_k: Any):
        called["plan"] += 1
        raise AssertionError("plan_turn must not run on DM agentic")

    async def fake_terra(turn: CustomerTurn, **_k: Any) -> TurnResult:
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="ok")],
            ),
            extra=dict(turn.extra or {}),
        )

    monkeypatch.setattr("services.brain.planner.openai_plan.plan_turn", boom)
    monkeypatch.setattr("services.brain.planner.openai_plan.plan_with_openai", boom)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _found_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", fake_terra)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a: Any, **_k: Any):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", no_sem)
    turn = CustomerTurn(tenant_id="t-freeze", conversation_id="c1", event_ids=["m1"], channel="whatsapp")
    result = await run_dm_after_gates(turn, message="how much is laser?", channel="whatsapp")
    assert called["plan"] == 0
    assert result.envelope.decision == "reply"


@pytest.mark.asyncio
async def test_one_terra_session_can_call_request_tool_then_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def fake_llm(**_k: Any):
        calls["n"] += 1
        if calls["n"] == 1:
            return _completion(name="start_request", arguments='{"request_type":"ORDER","title":"kit"}')
        return _completion(content="Got it — I started the order draft.")

    monkeypatch.setattr("services.brain.agent.terra_turn.openai_configured", lambda: True)
    monkeypatch.setattr("services.brain.agent.terra_session.openai_customer_tools", lambda: [])
    monkeypatch.setattr("services.brain.llm_core_service.create_chat_completion", fake_llm)
    monkeypatch.setattr("services.billing.membership.provider_expense.record_pending_provider", lambda **_k: None)
    monkeypatch.setattr("services.brain.providers.config.answer_model", lambda: "gpt-test")
    monkeypatch.setattr("services.brain.billing.operation_id_for_turn", lambda _t: "op-1")
    monkeypatch.setattr("services.brain.identity.load_identity_bundle", lambda _tid: None)
    monkeypatch.setattr("services.brain.agent.generate_path.coverage_ok", lambda *_a, **_k: True)
    monkeypatch.setattr("services.brain.agent.terra_turn.verify_answer", _pass_verify)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", _found_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a: Any, **_k: Any):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", no_sem)
    turn = CustomerTurn(tenant_id="t-one", conversation_id="c-one", event_ids=["m1"], customer_id="u1")
    result = await run_dm_after_gates(turn, message="I want to order the kit", channel="whatsapp")
    assert calls["n"] <= 2
    assert result.envelope.decision == "reply"
    assert (
        "order" in (result.envelope.reply_text or "").lower() or "draft" in (result.envelope.reply_text or "").lower()
    )
    assert result.extra.get("awaiting_confirmation") is True
    assert (result.extra or {}).get("terra_llm_calls", 0) <= 2


async def _pass_verify(**_k: Any):
    return SimpleNamespace(verdict="PASS", unsupported_claims=[], missing_tasks=[], repair_instruction="")


@pytest.mark.asyncio
async def test_comment_invite_does_not_start_request(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_terra(turn: CustomerTurn, **kwargs: Any) -> TurnResult:
        extra = dict(kwargs.get("extra") or turn.extra or {})
        assert extra.get("comment_invite_dm") is True
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="Message us in DM to finish.")],
            ),
            extra=extra,
        )

    async def fake_retrieve(*_a: Any, **_k: Any):
        return EvidenceBundle(outcome="not_found"), [], {}

    monkeypatch.setattr(
        "services.brain.actions.requests.persist_request",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no persist")),
    )
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", fake_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", fake_terra)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    turn = CustomerTurn(
        tenant_id="brain-shop",
        customer_id="u1",
        conversation_id="c-order-comment",
        channel="instagram_comment",
        surface="comment",
        invocation_kind="comment",
        event_ids=["c2"],
        extra={"comment_mode": "ai_comment", "response_language": "en"},
    )
    from services.brain.agent.loop import run_agentic_turn
    from tests.plan_builders import explicit_plan

    result = await run_agentic_turn(
        turn,
        "I want to order this",
        "instagram_comment",
        plan=explicit_plan("I want to order this", ("product_request", ["products"])),
    )
    assert "dm" in " ".join(item.text for item in result.envelope.messages).lower()
    assert result.extra.get("comment_invite_dm") is True
    assert not any(item.get("action_type") == "start_request" for item in result.extra.get("receipts") or [])
