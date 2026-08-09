"""Owner chat auto-title from first user message."""

from __future__ import annotations

from services.owner_chat_store import (
    OwnerChatStore,
    auto_title_from_first_message,
    is_default_conversation_title,
)


def test_auto_title_collapses_whitespace_and_truncates() -> None:
    assert auto_title_from_first_message("  hello\nworld  ") == "hello world"
    long = "x" * 80
    assert auto_title_from_first_message(long) == "x" * 60
    assert auto_title_from_first_message("كيف أربط انستغرام؟") == "كيف أربط انستغرام؟"
    assert auto_title_from_first_message("   ") == "New chat"


def test_default_title_detection() -> None:
    assert is_default_conversation_title("New chat")
    assert is_default_conversation_title("Chat")
    assert is_default_conversation_title("")
    assert not is_default_conversation_title("كيف أربط انستغرام؟")
    assert not is_default_conversation_title("My renamed chat")


def test_append_message_auto_titles_once(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path)
    conv = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    assert conv.title == "New chat"

    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="كيف أربط انستغرام؟\nplease help",
    )
    after = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=conv.id)
    assert after is not None
    assert after.title == "كيف أربط انستغرام؟ please help"

    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="second message should not overwrite",
    )
    after2 = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=conv.id)
    assert after2 is not None
    assert after2.title == "كيف أربط انستغرام؟ please help"

    store.rename(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        title="Manual title",
    )
    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="third",
    )
    after3 = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=conv.id)
    assert after3 is not None
    assert after3.title == "Manual title"

    listed = store.list_conversations(tenant_id="t1", user_id="u1")
    assert listed[0]["title"] == "Manual title"
