"""Comment HISTORY is injected into a later DM turn for the same author."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.brain.comments.dm_bridge import COMMENT_BRIDGE_POLICY_NOTE, remember_comment_thread
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn, HistorySnapshot, VisibleMessage
from services.brain.conversation_history import record_turn_history
from services.brain.conversation_store import reset_conversation_store_for_tests


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    reset_conversation_store_for_tests()


def test_remember_and_merge_comment_into_dm() -> None:
    from services.brain.comments.dm_bridge import merge_comment_history_into_dm

    turn = CustomerTurn(
        tenant_id="shop",
        customer_id="ig:user-9",
        conversation_id="comment:shop:instagram_comment:p1:ig:user-9",
        channel="instagram_comment",
        surface="comment",
        extra={"post_id": "p1"},
    )
    record_turn_history(
        turn,
        inbound_id="c1",
        inbound_text="how much is laser?",
        result=TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="it's 90")],
            ),
        ),
        comment_surface=True,
    )
    remember_comment_thread(turn)
    history = HistorySnapshot(messages=[VisibleMessage(id="dm1", role="user", text="ok", is_current_inbound=True)])
    merged, notes = merge_comment_history_into_dm(
        history,
        tenant_id="shop",
        user_id="ig:user-9",
        channel="instagram_dm",
        current_inbound_id="dm1",
        current_inbound_text="ok",
    )
    texts = [item.text for item in merged.messages]
    assert "how much is laser?" in texts
    assert "it's 90" in texts
    assert "ok" in texts
    assert COMMENT_BRIDGE_POLICY_NOTE in notes


@pytest.mark.asyncio
async def test_dm_followup_sees_comment_history(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = CustomerTurn(
        tenant_id="bridge-shop",
        customer_id="user-9",
        conversation_id="comment:bridge-shop:instagram_comment:p1:user-9",
        channel="instagram_comment",
        surface="comment",
        extra={"post_id": "p1"},
    )
    record_turn_history(
        turn,
        inbound_id="c1",
        inbound_text="price on the facial?",
        result=TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="90 USD")],
            ),
        ),
        comment_surface=True,
    )

    monkeypatch.setattr("services.brain.runtime.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": True, "reason": "", "detail": {}})(),
    )
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda item: item)
    monkeypatch.setattr(
        "services.brain.runtime.load_history_snapshot",
        AsyncMock(return_value=HistorySnapshot()),
    )

    captured: dict[str, object] = {}

    async def fake_billed(turn_obj, *, message, channel):
        captured["history"] = [item.text for item in turn_obj.history.messages]
        captured["notes"] = list((turn_obj.extra or {}).get("policy_notes") or [])
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="still 90")],
            ),
        )

    monkeypatch.setattr("services.brain.runtime._run_billed", fake_billed)

    from services.billing.entitlements_service import entitlements_store
    from services.brain.runtime import run_customer_ai_dm

    entitlements_store.set_plan(tenant_id="bridge-shop", plan_id="starter", status="active", source="admin")
    outcome = await run_customer_ai_dm(
        tenant_id="bridge-shop",
        message="ok",
        channel="instagram_dm",
        conversation_id="ig-thread-9",
        user_id="user-9",
        message_id="m-dm-1",
    )
    assert outcome.stop is False
    assert "price on the facial?" in captured["history"]
    assert "90 USD" in captured["history"]
    assert COMMENT_BRIDGE_POLICY_NOTE in captured["notes"]
