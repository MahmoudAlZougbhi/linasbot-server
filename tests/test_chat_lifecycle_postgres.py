"""Postgres inbox state survives operator actions and later customer messages."""

from __future__ import annotations

import pytest

from services.persistence.chat_store import append_message, get_thread, update_thread_lifecycle


@pytest.fixture()
def chat_db(monkeypatch: pytest.MonkeyPatch, tmp_path):
    from db.session import reset_engine_for_tests

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/chat.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    yield
    reset_engine_for_tests()


def test_customer_message_does_not_reset_waiting_state(chat_db) -> None:
    del chat_db
    append_message(
        user_id="whatsapp:961700000",
        role="user",
        text_body="hello",
        conversation_id="conv-1",
        metadata={"tenant_id": "tenant-a"},
    )
    assert update_thread_lifecycle(
        "tenant-a",
        "conv-1",
        conversation_state="waiting_for_operator",
        human_takeover_active=1,
    )
    append_message(
        user_id="whatsapp:961700000",
        role="user",
        text_body="still here",
        conversation_id="conv-1",
        metadata={"tenant_id": "tenant-a"},
        conversation_state="bot_active",
    )
    thread = get_thread("tenant-a", "conv-1")
    assert thread is not None
    assert thread["conversation_state"] == "waiting_for_operator"
    assert int(thread["unread_count"]) == 2
    assert int(thread["message_count"]) == 2
    assert get_thread("tenant-b", "conv-1") is None


def test_end_marks_resolved_without_a_document_store(chat_db) -> None:
    del chat_db
    append_message(
        user_id="web:guest-1",
        role="user",
        text_body="hi",
        conversation_id="web:tenant-a:guest-1",
        metadata={"tenant_id": "tenant-a", "channel": "web"},
        channel="web",
    )
    assert update_thread_lifecycle(
        "tenant-a",
        "web:tenant-a:guest-1",
        conversation_state="resolved",
        operator_id="",
        human_takeover_active=0,
        unread_count=0,
    )
    thread = get_thread("tenant-a", "web:tenant-a:guest-1")
    assert thread is not None
    assert thread["conversation_state"] == "resolved"
    assert int(thread["unread_count"]) == 0
