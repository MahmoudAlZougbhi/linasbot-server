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
async def test_v2_creative_request_refused_no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.orchestrator import run_owner_turn

    monkeypatch.setenv("OWNER_COPILOT_V2", "true")
    monkeypatch.setattr("services.billing.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: False)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_begin", _fake_turn_credit)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_on_event", lambda *_a, **_k: None)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_finalize", lambda *_a, **_k: None)
    monkeypatch.setattr("services.owner_copilot.message_billing.owner_turn_hold_abort", lambda *_a, **_k: None)
    monkeypatch.setattr("services.owner_copilot.context.pack_owner_turn_context", _stub_context)

    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="I want to create a post with an image",
    )
    assert turn.creative_draft is None
    assert "DMs and comments" in turn.reply_text or "comments" in turn.reply_text.lower()
    assert turn.route and turn.route.get("reason") == "creative_cancelled"
