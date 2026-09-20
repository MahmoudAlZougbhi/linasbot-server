"""Owner chat titles are named by Sol, not copied from the first owner message."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.owner_copilot.chat_store import OwnerChatStore, is_default_conversation_title
from services.owner_copilot.conversation_title import (
    maybe_assign_sol_title,
    sanitize_sol_chat_title,
    sse_title_if_named,
)


def test_default_title_detection() -> None:
    assert is_default_conversation_title("New chat")
    assert is_default_conversation_title("Chat")
    assert is_default_conversation_title("")
    assert is_default_conversation_title("Linas AI")
    assert not is_default_conversation_title("كيف أربط انستغرام؟")
    assert not is_default_conversation_title("My renamed chat")


def test_sanitize_rejects_verbatim_owner_copy_and_defaults() -> None:
    assert sanitize_sol_chat_title("New chat") is None
    assert sanitize_sol_chat_title('  "Instagram linking"  ') == "Instagram linking"
    owner = "كيف أربط انستغرام؟ please help"
    assert sanitize_sol_chat_title(owner, user_text=owner) is None
    assert sanitize_sol_chat_title("Instagram linking", user_text=owner) == "Instagram linking"


def test_sse_title_if_named_skips_placeholder() -> None:
    assert sse_title_if_named("New chat") is None
    assert sse_title_if_named("Hours and location") == {"title": "Hours and location"}


def test_append_message_does_not_copy_owner_text_as_title(tmp_path) -> None:
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
    assert after.title == "New chat"


@pytest.mark.asyncio
async def test_maybe_assign_sol_title_persists_once(tmp_path, monkeypatch) -> None:
    store = OwnerChatStore(root=tmp_path)
    conv = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="How do I connect Instagram?",
    )
    monkeypatch.setattr(
        "services.owner_copilot.conversation_title.owner_chat_store",
        store,
    )
    monkeypatch.setattr(
        "services.owner_copilot.conversation_title.propose_sol_chat_title",
        AsyncMock(return_value="Instagram connection"),
    )
    named = await maybe_assign_sol_title(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        user_text="How do I connect Instagram?",
        reply_text="Open Integrations, then Instagram.",
        language="en",
    )
    assert named == "Instagram connection"
    after = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=conv.id)
    assert after is not None
    assert after.title == "Instagram connection"

    monkeypatch.setattr(
        "services.owner_copilot.conversation_title.propose_sol_chat_title",
        AsyncMock(return_value="Should not overwrite"),
    )
    again = await maybe_assign_sol_title(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        user_text="How do I connect Instagram?",
        reply_text="Open Integrations, then Instagram.",
        language="en",
    )
    assert again is None
    after2 = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=conv.id)
    assert after2 is not None
    assert after2.title == "Instagram connection"


@pytest.mark.asyncio
async def test_maybe_assign_skips_after_first_user_turn(tmp_path, monkeypatch) -> None:
    store = OwnerChatStore(root=tmp_path)
    conv = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    store.append_message(tenant_id="t1", user_id="u1", conversation_id=conv.id, role="user", content="first")
    store.append_message(tenant_id="t1", user_id="u1", conversation_id=conv.id, role="user", content="second")
    monkeypatch.setattr("services.owner_copilot.conversation_title.owner_chat_store", store)
    propose = AsyncMock(return_value="Should not run")
    monkeypatch.setattr("services.owner_copilot.conversation_title.propose_sol_chat_title", propose)
    named = await maybe_assign_sol_title(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        user_text="second",
        reply_text="ok",
        language="en",
    )
    assert named is None
    propose.assert_not_called()


def test_manual_rename_survives_later_user_messages(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path)
    conv = store.create_conversation(tenant_id="t1", user_id="u1", greeting_text="Hi")
    store.rename(tenant_id="t1", user_id="u1", conversation_id=conv.id, title="Manual title")
    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="third",
    )
    after = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=conv.id)
    assert after is not None
    assert after.title == "Manual title"
