"""SEC-047: handle_message must not log phone numbers or message previews."""

from __future__ import annotations

import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import config
from handlers.text_handlers_message import handle_message

_FORBIDDEN_LOG_PATTERNS = (
    "phone_number from user_data",
    "phone_number from config",
    "raw_msg preview",
    "HANDLE_MESSAGE: About to save USER message",
)


def test_text_handlers_message_source_excludes_sec047_debug_patterns() -> None:
    source = Path("handlers/text_handlers_message.py").read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_LOG_PATTERNS:
        assert pattern not in source, f"forbidden log pattern still present: {pattern!r}"


@pytest.mark.asyncio
async def test_session_greeting_send_has_task_local_semantic_purpose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.meta_outbound_attempts import current_meta_outbound_send_purpose

    user_id = "facebook:semantic-greeting"
    user_data = {
        "phone_number": f"room:{user_id}",
        "current_conversation_id": "conv-semantic-greeting",
        "tenant_id": "linas",
        "channel": "facebook",
        "user_preferred_lang": "ar",
        "initial_user_query_to_process": None,
        "last_user_message_at": datetime.datetime.now() - datetime.timedelta(hours=13),
        "_dashboard_test_simulation": True,
    }
    observed: list[str] = []

    async def send(*_args: object, **_kwargs: object) -> None:
        observed.append(current_meta_outbound_send_purpose())

    async def noop(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr("handlers.text_handlers_message._delayed_process_messages", noop)
    monkeypatch.setattr(
        "handlers.text_handlers_message.maybe_send_takeover_autoreply",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr("handlers.text_handlers_message.get_firestore_db", lambda: None)
    monkeypatch.setattr(
        "handlers.text_handlers_message.sentiment_service.analyze_sentiment",
        lambda **_: {"sentiment": "neutral"},
    )
    monkeypatch.setattr(config, "AI_PRIMARY_ORCHESTRATION", False)
    config.user_greeting_stage[user_id] = 0
    config.user_gender[user_id] = "unknown"
    try:
        await handle_message(
            user_id=user_id,
            user_name="Test User",
            user_input_text="question",
            user_data=user_data,
            send_message_func=send,
            send_action_func=noop,
            skip_firestore_save=True,
            message_combine_delay=0.0,
        )
    finally:
        for mapping in (
            config.user_pending_messages,
            config.user_context,
            config.user_data_whatsapp,
            config.user_greeting_stage,
            config.user_last_bot_response_time,
            config.user_names,
            config.user_gender,
            config.gender_attempts,
            config.user_in_training_mode,
            config.user_photo_analysis_count,
            config.user_in_human_takeover_mode,
        ):
            mapping.pop(user_id, None)

    assert observed == ["session_greeting"]
    assert current_meta_outbound_send_purpose() == "primary_reply"


@pytest.mark.asyncio
async def test_handle_message_does_not_log_phone_or_message_preview(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user_id = "wa:user-sec047"
    phone_number = "+15551234567"
    user_message = "UNIQUE-SECRET-MESSAGE-BODY-SEC047"

    user_data = {
        "phone_number": phone_number,
        "current_conversation_id": "conv-sec047",
        "tenant_id": "tenant-sec047",
        "user_preferred_lang": "ar",
        "initial_user_query_to_process": None,
        "_dashboard_test_simulation": True,
    }

    async def noop_save(*_args, **_kwargs) -> None:
        return None

    async def noop_send(_uid: str, _msg: str) -> None:
        return None

    async def noop_action(_uid: str) -> None:
        return None

    monkeypatch.setattr(
        "handlers.text_handlers_message.save_conversation_message_to_firestore",
        noop_save,
    )
    monkeypatch.setattr(
        "handlers.text_handlers_message._delayed_process_messages",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "handlers.text_handlers_message.maybe_send_takeover_autoreply",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr("handlers.text_handlers_message.get_firestore_db", lambda: None)
    monkeypatch.setattr(
        "handlers.text_handlers_message.get_canonical_user_id_and_phone",
        lambda uid, phone: (uid, phone),
    )
    monkeypatch.setattr(
        "handlers.text_handlers_message.sentiment_service.analyze_sentiment",
        lambda **_: {"sentiment": "neutral"},
    )
    monkeypatch.setattr(config, "AI_PRIMARY_ORCHESTRATION", True)
    monkeypatch.setattr(config, "MAX_TEXT_LINES_PER_SINGLE_MESSAGE", 100)

    config_keys = (
        "user_pending_messages",
        "user_context",
        "user_data_whatsapp",
        "user_greeting_stage",
        "user_last_bot_response_time",
        "user_names",
        "user_gender",
        "gender_attempts",
        "user_in_training_mode",
        "user_photo_analysis_count",
        "user_in_human_takeover_mode",
    )
    try:
        await handle_message(
            user_id=user_id,
            user_name="Test User",
            user_input_text=user_message,
            user_data=user_data,
            send_message_func=noop_send,
            send_action_func=noop_action,
            message_combine_delay=0.0,
        )
    finally:
        for key in config_keys:
            getattr(config, key).pop(user_id, None)

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert phone_number not in combined
    assert user_message not in combined
    for pattern in _FORBIDDEN_LOG_PATTERNS:
        assert pattern not in combined
