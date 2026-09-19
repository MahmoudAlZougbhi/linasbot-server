"""TikTok nested replies reach Terra with per-author HISTORY."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.brain.contracts.turn import HistorySnapshot, VisibleMessage
from services.integrations.tiktok.comment_sync import should_enqueue_comment_ai
from services.integrations.tiktok.comment_webhook import handle_comment_webhook


@pytest.mark.asyncio
async def test_comment_webhook_does_not_drop_nested_replies() -> None:
    out = await handle_comment_webhook(
        payload={},
        content={"parent_comment_id": "parent-1", "comment_id": "c2", "comment_action": "insert"},
        event_name="comment.update",
    )
    assert out.get("reason") != "reply"
    assert out.get("skipped") is True


def test_should_enqueue_nested_visitor_reply() -> None:
    connected = datetime(2026, 8, 24, 16, 34, tzinfo=UTC)
    assert (
        should_enqueue_comment_ai(
            created=True,
            is_reply=True,
            payload={"owner": False},
            create_time=connected + timedelta(minutes=1),
            connected_at=connected,
        )
        is True
    )


@pytest.mark.asyncio
async def test_tiktok_reply_loads_author_history(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: dict[str, str] = {}

    async def fake_history(**kwargs):
        loaded.update({key: str(kwargs.get(key) or "") for key in ("user_id", "conversation_id")})
        return HistorySnapshot(messages=[VisibleMessage(id="old", role="user", text="price on the reel?")])

    monkeypatch.setattr("services.brain.runtime.load_history_snapshot", fake_history)
    monkeypatch.setattr("services.brain.runtime.winning_comment_mode", lambda **_k: (None, None))
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": True, "reason": "", "detail": {}})(),
    )
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda turn: turn)

    captured: dict[str, object] = {}

    async def fake_run(turn, *, message, channel):
        captured["history"] = [item.text for item in turn.history.messages]
        captured["conversation_id"] = turn.conversation_id
        from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult

        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="ok")],
            ),
        )

    monkeypatch.setattr("services.brain.runtime.run_dm_after_gates", fake_run)
    monkeypatch.setattr(
        "services.brain.comments.pipeline.apply_ai_comment_destinations",
        lambda result, _mode, **_k: result,
    )
    monkeypatch.setattr("services.brain.runtime.apply_message_billing", lambda _turn, result: result)

    from services.billing.entitlements_service import entitlements_store
    from services.brain.runtime import run_customer_ai_comment

    entitlements_store.set_plan(tenant_id="tt-shop", plan_id="pro", status="active", source="admin")
    monkeypatch.setattr("services.brain.runtime.assert_channel_plan_allowed", lambda *_a, **_k: None)
    outcome = await run_customer_ai_comment(
        tenant_id="tt-shop",
        comment_text="ok what color",
        comment_id="c-reply",
        post_id="video-9",
        channel="tiktok_comment",
        provider_sender_id="mustapha",
        parent_comment="we have three shades",
        parent_is_page=True,
    )
    assert outcome.stop is False
    assert loaded["conversation_id"] == "comment:tt-shop:tiktok_comment:video-9:mustapha"
    assert loaded["user_id"] == "mustapha"
    assert "price on the reel?" in captured["history"]
    assert "we have three shades" in captured["history"]
    assert captured["conversation_id"] == loaded["conversation_id"]
