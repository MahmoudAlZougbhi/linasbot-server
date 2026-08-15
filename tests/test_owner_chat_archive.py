"""Owner conversation archive via PATCH."""

from __future__ import annotations

from services.owner_chat_store import OwnerChatStore


def test_set_archived_roundtrip(tmp_path):
    store = OwnerChatStore(root=tmp_path)
    conv = store.create_conversation(tenant_id="t1", user_id="u1", title="Greeting", greeting_text="Hi")
    store.append_message(
        tenant_id="t1",
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="hello",
    )
    assert conv.archived is False
    assert store.set_archived(tenant_id="t1", user_id="u1", conversation_id=conv.id, archived=True)
    listed = store.list_conversations(tenant_id="t1", user_id="u1")
    row = next(r for r in listed if r["id"] == conv.id)
    assert row["archived"] is True
    assert store.set_archived(tenant_id="t1", user_id="u1", conversation_id=conv.id, archived=False)
    listed2 = store.list_conversations(tenant_id="t1", user_id="u1")
    row2 = next(r for r in listed2 if r["id"] == conv.id)
    assert row2["archived"] is False
