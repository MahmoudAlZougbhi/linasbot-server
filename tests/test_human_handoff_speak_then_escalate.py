"""HUMAN: Terra may speak, then escalate_to_human. Live Chat only. No canned protocol."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from services.brain.agent.loop import run_agentic_turn
from services.brain.contracts.actions import ActionReceipt
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage
from services.brain.contracts.turn import CustomerTurn
from services.brain.verify.critic import VerifierResult
from tests.plan_builders import explicit_plan

ROOT = Path(__file__).resolve().parents[1]


def _human_rules(*, hint: str = "Say one short line, then the team will continue.") -> dict:
    return {
        "module_enabled": True,
        "enabled_types": ["HUMAN"],
        "rules": [
            {
                "id": "h1",
                "type": "HUMAN",
                "name": "Staff",
                "enabled": True,
                "notes": "Be warm",
                "handoff_guidance": "Stay brief",
                "pre_handoff_message_hint": hint,
            }
        ],
    }


@pytest.mark.asyncio
async def test_human_hint_terra_then_live_chat_no_board_card(monkeypatch: pytest.MonkeyPatch) -> None:
    message = "I need a person"
    plan = explicit_plan(message, ("human_request", ["none"]))
    escalated = {"n": 0}

    async def fake_escalate(**_k):
        escalated["n"] += 1
        return ActionReceipt(action_id="handoff:t1", action_type="escalate_to_human", state="success")

    async def fake_generate(**_k):
        return FinalReplyEnvelope(
            decision="reply",
            messages=[
                OutboundMessage(destination="instagram_dm:u1", text="One moment — connecting you with the team.")
            ],
            dispositions={"t1": "awaiting_customer"},
        )

    async def fake_verify(**_k):
        return VerifierResult(verdict="PASS")

    async def fake_retrieve(*_a, **_k):
        return EvidenceBundle(outcome="not_found"), [], {}

    def boom_persist(*_a, **_k):
        raise AssertionError("HUMAN must not create a Requests board card")

    monkeypatch.setattr(
        "services.brain.planner.published_rules.published_requests_payload",
        lambda _tid: _human_rules(),
    )
    monkeypatch.setattr("services.brain.actions.execute.escalate_to_human", fake_escalate)
    monkeypatch.setattr("services.brain.actions.requests.persist_request", boom_persist)
    monkeypatch.setattr("services.brain.agent.generate_path.openai_configured", lambda: True)
    monkeypatch.setattr("services.brain.agent.generate_path.generate_grounded_reply", fake_generate)
    monkeypatch.setattr("services.brain.agent.generate_path.verify_answer", fake_verify)
    monkeypatch.setattr("services.brain.agent.generate_path.load_identity_bundle", lambda _tid: None)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", fake_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.agent.loop._maybe_tool_calls", AsyncMock(return_value=([], [], 0)))

    turn = CustomerTurn(
        tenant_id="brain-shop",
        customer_id="u1",
        conversation_id="c-hint",
        event_ids=["m3"],
        channel="instagram_dm",
    )
    result = await run_agentic_turn(turn, message, "instagram_dm", plan=plan)
    texts = [item.text for item in result.envelope.messages]
    assert any("connecting you" in text.lower() for text in texts)
    assert result.extra.get("handoff_ok") is True
    assert escalated["n"] == 1
    assert not any(item.get("action_type") == "start_request" for item in result.extra.get("receipts") or [])
    src = (ROOT / "services/brain/agent/action_gate.py").read_text(encoding="utf-8")
    assert "never append protocol text" in src
    assert not (ROOT / "services/requests/human_detect.py").exists()
