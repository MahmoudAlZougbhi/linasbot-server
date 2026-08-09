"""Owner conversation message paging (latest window + before cursor)."""

from __future__ import annotations

from services.owner_chat_store import OwnerChatMessage, OwnerChatStore


def _fill(store: OwnerChatStore, *, tenant_id: str, user_id: str, n: int) -> str:
    conv = store.create_conversation(tenant_id=tenant_id, user_id=user_id, greeting_text="hi")
    for i in range(n):
        store.append_message(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conv.id,
            role="user" if i % 2 == 0 else "assistant",
            content=f"m{i}",
        )
    return conv.id


def test_slice_messages_latest_window() -> None:
    msgs = [
        OwnerChatMessage(id=f"id{i}", role="user", content=str(i), created_at=float(i)) for i in range(10)
    ]
    page, has_more, total = OwnerChatStore.slice_messages(msgs, limit=3)
    assert total == 10
    assert has_more is True
    assert [m.id for m in page] == ["id7", "id8", "id9"]


def test_slice_messages_before_cursor() -> None:
    msgs = [
        OwnerChatMessage(id=f"id{i}", role="user", content=str(i), created_at=float(i)) for i in range(10)
    ]
    page, has_more, total = OwnerChatStore.slice_messages(msgs, limit=3, before_id="id7")
    assert total == 10
    assert has_more is True
    assert [m.id for m in page] == ["id4", "id5", "id6"]
    page2, has_more2, _ = OwnerChatStore.slice_messages(msgs, limit=10, before_id="id4")
    assert has_more2 is False
    assert [m.id for m in page2] == ["id0", "id1", "id2", "id3"]


def test_store_get_then_slice(tmp_path) -> None:
    store = OwnerChatStore(root=tmp_path)
    cid = _fill(store, tenant_id="t1", user_id="u1", n=40)
    conv = store.get_conversation(tenant_id="t1", user_id="u1", conversation_id=cid)
    assert conv is not None
    # greeting + 40 = 41
    page, has_more, total = store.slice_messages(conv.messages, limit=25)
    assert total == 41
    assert has_more is True
    assert len(page) == 25
    older, has_more2, _ = store.slice_messages(conv.messages, limit=25, before_id=page[0].id)
    assert len(older) == 16
    assert has_more2 is False
    assert older[-1].id != page[0].id
