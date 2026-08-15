"""Meta DM turn evidence must be batch-scoped and never leak between messages."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

import pytest

import config
from handlers import text_handlers_delayed
from services.ai_reply_lifecycle import get_turn, persist_generated_reply
from services.ai_reply_turn_runtime import finalize_delivery


@pytest.mark.asyncio
async def test_sequential_sender_turns_rotate_meta_delivery_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.ai_reply_lifecycle as lifecycle
    import services.ai_reply_turn_runtime as turn_runtime

    turns = tmp_path / "ai_reply_turns"
    turns.mkdir()
    monkeypatch.setattr(lifecycle, "_store_dir", lambda: turns)
    monkeypatch.setattr(turn_runtime, "try_reserve_for_ai", lambda _user_data: True)
    monkeypatch.setattr(turn_runtime, "pending_delivery_for_claim", lambda _basis: None)

    async def _claim(*_args: Any, **_kwargs: Any) -> bool:
        return True

    async def _claim_done(*_args: Any, **_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(text_handlers_delayed, "try_claim_ai_turn", _claim)
    monkeypatch.setattr("services.outbound_turn_idempotency.complete_ai_turn_claim", _claim_done)
    monkeypatch.setattr("services.outbound_turn_idempotency.release_ai_turn_claim", _claim_done)

    user_id = "instagram:sequential-evidence"
    user_data: dict[str, Any] = {
        "tenant_id": "linas",
        "channel": "instagram",
        "phone_number": f"room:{user_id}",
        "_text_turn_epoch": 1,
        "_batch_inbound_mids": ["meta-inbound-1"],
    }
    config.user_names[user_id] = "Test customer"
    config.user_pending_messages[user_id] = deque(["first question"])
    outbound_counter = 0

    async def _send(
        _user_id: str,
        message_text: str | None = None,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> dict[str, Any]:
        nonlocal outbound_counter
        del message_text, image_url, audio_url
        outbound_counter += 1
        return {
            "success": True,
            "provider": "meta",
            "message_id": f"meta-outbound-{outbound_counter}",
        }

    async def _typing(_user_id: str) -> dict[str, bool]:
        return {"success": True}

    should_send = True

    async def _respond(_user_id: str, **kwargs: Any) -> None:
        if not should_send:
            return
        logical_reply_id = str(kwargs["user_data"]["_logical_reply_id"])
        persist_generated_reply(logical_reply_id, reply_text="test reply")
        await kwargs["send_message_func"](_user_id, message_text="test reply")

    monkeypatch.setattr(text_handlers_delayed, "_process_and_respond", _respond)
    try:
        await text_handlers_delayed._delayed_process_messages(
            user_id,
            user_data,
            _send,
            _typing,
            combine_delay_seconds=0.0,
            text_turn_epoch=1,
        )
        first_logical_id = str(user_data["_logical_reply_id"])
        first = get_turn(first_logical_id)
        assert first is not None
        assert first.provider_reply_id == "meta-outbound-1"
        assert finalize_delivery({"user_data": user_data})["provider_message_id_present"] is True

        # Reuse the exact conversation dict for a later inbound turn. A missing
        # send on turn two must not reuse turn one's logical ID or message ID.
        should_send = False
        user_data["_batch_inbound_mids"] = ["meta-inbound-2"]
        user_data["_text_turn_epoch"] = 2
        config.user_pending_messages[user_id].append("second question")
        await text_handlers_delayed._delayed_process_messages(
            user_id,
            user_data,
            _send,
            _typing,
            combine_delay_seconds=0.0,
            text_turn_epoch=2,
        )

        second_logical_id = str(user_data["_logical_reply_id"])
        second = get_turn(second_logical_id)
        assert second_logical_id != first_logical_id
        assert second is not None
        assert second.provider_reply_id is None
        summary = finalize_delivery({"user_data": user_data})
        assert summary["delivery"] != "delivered"
        assert summary["provider_message_id_present"] is False
        assert outbound_counter == 1
    finally:
        config.user_names.pop(user_id, None)
        config.user_pending_messages.pop(user_id, None)
        config.user_last_bot_response_time.pop(user_id, None)
