"""Empty owner chats stay out of history until the first user message."""

from __future__ import annotations

from services.owner_chat_store import OwnerChatStore, messages_include_user_turn


def test_greeting_only_conversation_is_absent_from_history(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path)
    conv = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    assert messages_include_user_turn([m.__dict__ for m in (conv.messages or [])]) is False
    assert store.list_conversations(tenant_id="t1", user_id="u1") == []


def test_history_includes_conversation_after_first_user_message(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path)
    empty = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    started = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=started.id,
        role="user",
        content="What is Linas?",
    )
    listed = store.list_conversations(tenant_id="t1", user_id="u1")
    ids = [row["id"] for row in listed]
    assert started.id in ids
    assert empty.id not in ids
    assert listed[0]["has_user_message"] is True


def test_creating_new_empty_chat_discards_previous_empty(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path)
    first = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    second = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    assert store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=first.id) is None
    kept = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=second.id)
    assert kept is not None
    assert store.list_conversations(tenant_id="t1", user_id="u1") == []
