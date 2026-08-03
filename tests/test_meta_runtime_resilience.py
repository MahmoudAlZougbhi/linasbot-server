"""Runtime resilience coverage for Meta social reply delivery."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from unittest import mock

import pytest

import config
from handlers import text_handlers_delayed


@pytest.mark.asyncio
async def test_typing_failure_does_not_abort_customer_reply_pipeline(capsys: pytest.CaptureFixture[str]) -> None:
    user_id = "facebook:typing-failure-test"
    user_data: dict[str, Any] = {
        "channel": "facebook",
        "phone_number": f"room:{user_id}",
        "_text_turn_epoch": 1,
    }
    config.user_pending_messages[user_id] = ["I want to book an appointment."]
    processed: list[str] = []

    async def failed_typing(_user_id: str) -> Any:
        raise RuntimeError("sensitive-provider-response-must-not-be-logged")

    async def unused_send(
        _user_id: str,
        message_text: str | None = None,
        image_url: str | None = None,
        audio_url: str | None = None,
    ) -> Any:
        return {
            "success": True,
            "message_text": message_text,
            "image_url": image_url,
            "audio_url": audio_url,
        }

    async def captured_process(_user_id: str, **kwargs: Any) -> None:
        processed.append(str(kwargs["user_input_to_process"]))

    send_func: Callable[..., Awaitable[Any]] = unused_send
    action_func: Callable[[str], Awaitable[Any]] = failed_typing
    try:
        with mock.patch.object(text_handlers_delayed, "_process_and_respond", side_effect=captured_process):
            await text_handlers_delayed._delayed_process_messages(
                user_id,
                user_data,
                send_func,
                action_func,
                combine_delay_seconds=0.0,
                text_turn_epoch=1,
            )
    finally:
        config.user_pending_messages.pop(user_id, None)
        config.user_last_bot_response_time.pop(user_id, None)

    captured = capsys.readouterr()
    assert processed == ["I want to book an appointment."], captured.out + captured.err
    assert "type=RuntimeError" in captured.out
    assert "sensitive-provider-response-must-not-be-logged" not in captured.out
    assert "sensitive-provider-response-must-not-be-logged" not in captured.err
