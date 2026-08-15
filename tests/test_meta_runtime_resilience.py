"""Runtime resilience coverage for Meta social reply delivery."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

import config
from handlers import text_handlers_delayed
from handlers.text_handlers_firestore import _delayed_processing_tasks
from modules import meta_messaging_webhook
from services import social_messaging_processor

ROOT = Path(__file__).resolve().parents[1]


def test_prod_runtime_diagnostic_recognizes_page_webhook_object() -> None:
    workflow = (ROOT / ".github" / "workflows" / "prod-preflight-readonly.yml").read_text(encoding="utf-8")

    assert 'r"object=(page|instagram) parsed=(\\d+) accepted=(\\d+) "' in workflow
    assert 'r"object=(facebook|instagram) parsed=' not in workflow


def test_prod_runtime_diagnostic_still_runs_after_preflight_failure() -> None:
    workflow = (ROOT / ".github" / "workflows" / "prod-preflight-readonly.yml").read_text(encoding="utf-8")

    assert "if: ${{ always() && inputs.include_meta_runtime_diagnostics }}" in workflow


@pytest.mark.asyncio
async def test_typing_failure_does_not_abort_customer_reply_pipeline(capsys: pytest.CaptureFixture[str]) -> None:
    user_id = "facebook:typing-failure-test"
    user_data: dict[str, Any] = {
        "channel": "facebook",
        "phone_number": f"room:{user_id}",
        "_text_turn_epoch": 1,
    }
    config.user_pending_messages[user_id].clear()
    config.user_pending_messages[user_id].append("I want to book an appointment.")
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


@pytest.mark.asyncio
async def test_background_failure_log_omits_exception_message(caplog: pytest.LogCaptureFixture) -> None:
    async def failed_background_work() -> None:
        raise RuntimeError("sensitive-webhook-payload-must-not-be-logged")

    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        task = asyncio.create_task(failed_background_work())
        meta_messaging_webhook._track_task(task)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "background_processing_failed type=RuntimeError" in rendered
    assert "sensitive-webhook-payload-must-not-be-logged" not in rendered


@pytest.mark.asyncio
async def test_older_meta_waiter_follows_replacement_without_removing_it() -> None:
    user_id = "instagram:rapid-same-sender"
    first_started = asyncio.Event()
    replacement_release = asyncio.Event()

    async def first_wave() -> None:
        first_started.set()
        await asyncio.Event().wait()

    async def replacement_wave() -> None:
        await replacement_release.wait()

    first = asyncio.create_task(first_wave())
    _delayed_processing_tasks[user_id] = first
    older_waiter = asyncio.create_task(social_messaging_processor._await_delayed_processing(user_id))
    await first_started.wait()

    replacement = asyncio.create_task(replacement_wave())
    first.cancel()
    _delayed_processing_tasks[user_id] = replacement
    await asyncio.sleep(0)
    assert not older_waiter.done()
    assert _delayed_processing_tasks[user_id] is replacement

    newer_waiter = asyncio.create_task(social_messaging_processor._await_delayed_processing(user_id))
    replacement_release.set()
    await asyncio.gather(older_waiter, newer_waiter)

    assert user_id not in _delayed_processing_tasks
    assert replacement.done()


def test_production_runtime_metric_parser_uses_real_meta_object_names() -> None:
    source = (Path(__file__).resolve().parents[1] / ".github/workflows/prod-preflight-readonly.yml").read_text(
        encoding="utf-8"
    )
    assert r"object=(page|instagram)" in source
    assert r"object=(facebook|instagram)" not in source
