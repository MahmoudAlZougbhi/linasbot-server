"""System Copilot V2: creative cancelled under OWNER_COPILOT_V2."""

from __future__ import annotations

from typing import Any

import pytest


def _stub_context(**_: Any) -> dict[str, Any]:
    return {
        "system_prompt": "x",
        "account_summary": {"setup_stage": "ready", "profile": {"preferred_language": "en"}},
        "knowledge_block": "",
        "capabilities": ["system_copilot"],
        "recent_messages": [],
        "conversation_summary": None,
        "reply_language": "en",
        "preferred_language": "en",
        "cm_full_dump": False,
        "full_history": False,
    }


def _fake_turn_credit(tenant_id: str, *, conversation_id: str = "", **_kwargs: Any) -> Any:
    from services.owner_copilot.message_billing import OwnerTurnHold

    return OwnerTurnHold(tenant_id=tenant_id, reservation_id="test-reservation")


@pytest.mark.asyncio
async def test_v2_creative_request_reaches_sol_no_pre_refuse(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from services.owner_copilot.orchestrator import run_owner_turn

    monkeypatch.setenv("OWNER_COPILOT_V2", "true")
    monkeypatch.setattr("services.billing.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: False)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_begin", _fake_turn_credit)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_on_event", lambda *_a, **_k: None)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_finalize", lambda *_a, **_k: None)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_abort", lambda *_a, **_k: None)
    monkeypatch.setattr("services.owner_copilot.context.pack_owner_turn_context", _stub_context)
    called = {"sol": False}

    async def fake_round(**_k):
        called["sol"] = True
        yield "delta", "Creative Studio is cancelled. I can help with AI Setup."
        yield (
            "result",
            SimpleNamespace(tool_calls=[], content="Creative Studio is cancelled. I can help with AI Setup."),
        )

    monkeypatch.setattr("services.owner_copilot.brain_stream_body.iter_sol_tool_round", fake_round)

    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="I want to create a post with an image",
    )
    assert called["sol"] is True
    assert turn.creative_draft is None
    assert "AI Setup" in turn.reply_text or "cancelled" in turn.reply_text.lower()
    assert (turn.route or {}).get("reason") != "creative_cancelled"
