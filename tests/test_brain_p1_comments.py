"""P1: restricted gates before static comments; no canned AI comment copy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.brain.comments.pipeline import apply_ai_comment_destinations, deterministic_comment_result
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.gates import GateDecision
from services.brain.runtime import _gate_result, _outcome


def test_static_comment_does_not_invent_sent_you_a_dm() -> None:
    generated = TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="reply",
            messages=[OutboundMessage(destination="dm", text="Private hours 10-8")],
        ),
        ai_called=True,
    )
    rewritten = apply_ai_comment_destinations(generated, "ai_both")
    texts = [item.text for item in rewritten.envelope.messages]
    dests = [item.destination for item in rewritten.envelope.messages]
    assert "Sent you a DM." not in texts
    assert "dm" in dests


def test_static_template_kept_verbatim() -> None:
    decision = SimpleNamespace(
        reply_text="Thanks for commenting!",
        dm_text="Here is the menu.",
        rule_id="r1",
        rule_mode="static_both",
    )
    result = deterministic_comment_result("static_both", decision, event_id="c1")
    assert result is not None
    public = next(item.text for item in result.envelope.messages if item.destination == "comment")
    private = next(item.text for item in result.envelope.messages if item.destination == "dm")
    assert public == "Thanks for commenting!"
    assert private == "Here is the menu."


def test_restricted_gate_outranks_static_comment_copy() -> None:
    turn = CustomerTurn(tenant_id="t1", surface="comment", channel="instagram", invocation_kind="comment")
    gate = GateDecision(allow=False, reason="restricted", reply_text="We cannot discuss that topic.", detail="medical")
    gated = _gate_result(turn, gate, "instagram_comment")
    outcome = _outcome(gated, comment_surface=True)
    assert gated.stop_reason == "restricted"
    assert gated.envelope.messages[0].text == "We cannot discuss that topic."
    assert outcome.reply == "We cannot discuss that topic."


@pytest.mark.asyncio
async def test_comment_runtime_evaluates_gates_before_static(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain import runtime

    called: dict[str, str] = {}

    def fake_gates(_turn, **_k):
        called["gates"] = "yes"
        return GateDecision(allow=False, reason="restricted", reply_text="Restricted.", detail="x")

    def fake_mode(**_k):
        called["mode"] = "too-late"
        return "static_comment", SimpleNamespace(reply_text="Hello from static", dm_text="", rule_id="r")

    monkeypatch.setattr("services.brain.tenant_gate.evaluate_brain_tenant_gate", lambda _t: {"allow": True})
    monkeypatch.setattr("services.brain.channel_plan.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.billing.membership.comment_gate.assert_comment_automation_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(runtime, "evaluate_gates", fake_gates)
    monkeypatch.setattr(runtime, "winning_comment_mode", fake_mode)
    monkeypatch.setattr(runtime, "record_turn_history", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime, "apply_live_control", lambda turn: turn)
    monkeypatch.setattr(runtime, "apply_message_billing", lambda _turn, result: result)
    out = await runtime.run_customer_ai_comment(
        tenant_id="t1",
        comment_text="buy pills",
        channel="instagram_comment",
        comment_id="c1",
    )
    assert called.get("gates") == "yes"
    assert called.get("mode") != "too-late"
    assert out.reply == "Restricted."


@pytest.mark.asyncio
async def test_static_comment_ignores_empty_message_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain import runtime

    def fake_gates(_turn, **_k):
        return GateDecision(True, "ok")

    def fake_mode(**_k):
        return "static_comment", SimpleNamespace(reply_text="Hello from static", dm_text="", rule_id="r")

    def boom(_tid):
        raise AssertionError("static comments must not require message balance")

    monkeypatch.setattr("services.brain.tenant_gate.evaluate_brain_tenant_gate", lambda _t: {"allow": True})
    monkeypatch.setattr("services.brain.channel_plan.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.billing.membership.comment_gate.assert_comment_automation_allowed",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(runtime, "evaluate_gates", fake_gates)
    monkeypatch.setattr(runtime, "winning_comment_mode", fake_mode)
    monkeypatch.setattr(runtime, "record_turn_history", lambda *_a, **_k: None)
    monkeypatch.setattr(runtime, "apply_live_control", lambda turn: turn)
    monkeypatch.setattr(runtime, "apply_message_billing", lambda _turn, result: result)
    monkeypatch.setattr("services.billing.membership.generative_gate.generative_block_reason", boom)
    out = await runtime.run_customer_ai_comment(
        tenant_id="t1",
        comment_text="nice post",
        channel="instagram_comment",
        comment_id="c2",
    )
    assert out.reply == "Hello from static"
