"""W4-A2: voice_handlers must not block the event loop on Firestore get."""

from __future__ import annotations

import asyncio
import io
from unittest.mock import AsyncMock, MagicMock

import pytest

import config
from handlers import voice_handlers


def _mock_firestore_db(doc_snap: MagicMock) -> MagicMock:
    conv_doc_ref = MagicMock()
    conv_doc_ref.get = MagicMock(return_value=doc_snap)

    conversations_coll = MagicMock()
    conversations_coll.document.return_value = conv_doc_ref

    user_doc_ref = MagicMock()
    user_doc_ref.collection.return_value = conversations_coll

    users_coll = MagicMock()
    users_coll.document.return_value = user_doc_ref

    artifacts_doc = MagicMock()
    artifacts_doc.collection.return_value = users_coll

    db = MagicMock()
    db.collection.return_value.document.return_value = artifacts_doc
    return db


@pytest.mark.asyncio
async def test_handle_voice_message_firestore_get_uses_asyncio_to_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = "wa:voice-async-test"
    conversation_id = "conv-voice-async"

    doc_snap = MagicMock()
    doc_snap.exists = True
    doc_snap.to_dict.return_value = {
        "human_takeover_active": True,
        "operator_name": "Operator Ali",
    }

    to_thread_calls: list[object] = []
    real_to_thread = asyncio.to_thread

    async def tracking_to_thread(func, *args, **kwargs):
        to_thread_calls.append(func)
        return await real_to_thread(func, *args, **kwargs)

    monkeypatch.setattr(voice_handlers, "PYDUB_AVAILABLE", True)
    monkeypatch.setattr(voice_handlers, "record_inbound_mid_for_ai_turn", lambda *_a, **_k: None)
    monkeypatch.setattr(
        voice_handlers,
        "save_conversation_message_to_firestore",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("utils.utils.get_firestore_db", lambda: _mock_firestore_db(doc_snap))
    monkeypatch.setattr(asyncio, "to_thread", tracking_to_thread)
    monkeypatch.setattr(
        "services.cm.capability_gates.voice_processing_enabled",
        lambda _tenant: True,
    )

    config.user_data_whatsapp[user_id] = {"current_conversation_id": conversation_id}
    send_message = AsyncMock()
    send_action = AsyncMock()

    user_data = {
        "tenant_id": "linas",
        "current_conversation_id": conversation_id,
        "user_preferred_lang": "ar",
        "phone_number": "+15559876543",
    }

    try:
        await voice_handlers.handle_voice_message(
            user_id=user_id,
            user_name="Voice User",
            audio_data_bytes=io.BytesIO(b"fake-audio"),
            user_data=user_data,
            send_message_func=send_message,
            send_action_func=send_action,
            audio_url="https://example.com/voice.ogg",
        )
    finally:
        config.user_data_whatsapp.pop(user_id, None)

    assert len(to_thread_calls) == 1
    send_message.assert_awaited_once()
    send_action.assert_not_awaited()
