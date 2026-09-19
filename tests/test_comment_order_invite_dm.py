"""Comment ORDER/APPOINTMENT: Terra invites DM. No persist. No system canned send."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.brain.agent.action_gate import apply_action_gate
from services.brain.agent.loop import run_agentic_turn
from services.brain.comments.pipeline import apply_ai_comment_destinations
from services.brain.contracts.evidence import EvidenceBundle
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from tests.plan_builders import explicit_plan

ROOT = Path(__file__).resolve().parents[1]


def test_dead_comment_capture_helper_is_gone() -> None:
    src = (ROOT / "services/requests/capture.py").read_text(encoding="utf-8")
    assert "comment_capture_policy_reply" not in src
    assert "public_comment_dm_invite" not in src
    assert "شكراً لتعليقك" not in src


@pytest.mark.asyncio
async def test_comment_booking_does_not_stage_or_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    message = "بدي موعد ليزر بكرا"
    plan = explicit_plan(message, ("service_request", ["services", "branches"]))
    turn = CustomerTurn(
        tenant_id="brain-shop",
        customer_id="u1",
        conversation_id="c-comment",
        channel="instagram_comment",
        surface="comment",
        invocation_kind="comment",
        event_ids=["c1"],
        extra={"comment_mode": "ai_comment"},
    )
    gated = await apply_action_gate(
        turn,
        plan,
        message=message,
        dest="comment",
        lang="ar",
        extra={},
        agent_trace=[],
    )
    assert gated.early is None
    assert gated.extra.get("comment_invite_dm") is True
    assert gated.extra.get("awaiting_confirmation") is not True
    assert not gated.extra.get("pending_actions")


@pytest.mark.asyncio
async def test_comment_order_terra_invites_dm_no_requests_card(monkeypatch: pytest.MonkeyPatch) -> None:
    message = "I want to order this"
    plan = explicit_plan(message, ("product_request", ["products"]))

    async def fake_terra(_turn, **_k):
        extra = dict(_k.get("extra") or {})
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[
                    OutboundMessage(
                        destination="comment",
                        text="Message us in DM and we will finish the order together.",
                    )
                ],
            ),
            extra=extra,
        )

    async def fake_retrieve(*_a, **_k):
        return EvidenceBundle(outcome="not_found"), [], {}

    def boom_persist(*_a, **_k):
        raise AssertionError("must not persist ORDER/APPOINTMENT from a public comment")

    monkeypatch.setattr("services.brain.actions.requests.persist_request", boom_persist)
    monkeypatch.setattr("services.brain.agent.loop.multi_round_retrieve", fake_retrieve)
    monkeypatch.setattr("services.brain.agent.loop.reserve_generative", lambda *_a, **_k: None)
    monkeypatch.setattr("services.brain.agent.loop.run_terra_turn", fake_terra)

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
    result = await run_agentic_turn(turn, message, "instagram_comment", plan=plan)
    blob = " ".join(item.text for item in result.envelope.messages).lower()
    assert "dm" in blob
    assert result.extra.get("awaiting_confirmation") is not True
    assert result.extra.get("comment_invite_dm") is True
    assert not any(item.get("action_type") == "start_request" for item in result.extra.get("receipts") or [])


def test_tiktok_comment_invite_stays_public() -> None:
    generated = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Continue in DM to finish booking.")],
        ),
        extra={"comment_mode": "ai_dm"},
    )
    rewritten = apply_ai_comment_destinations(generated, "ai_dm", channel="tiktok_comment")
    dests = [item.destination for item in rewritten.envelope.messages]
    assert dests == ["comment"]
    assert rewritten.envelope.messages[0].text == "Continue in DM to finish booking."
    assert rewritten.extra.get("tiktok_public_only") is True
