"""HIGH: tenant A never sees tenant B Live Chat threads."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from services.integrations.access_channels import filter_chats_for_session
from services.live_chat.contracts import utc_now
from services.live_chat.service import live_chat_service


class _Doc:
    def __init__(self, doc_id: str, data: dict) -> None:
        self.id = doc_id
        self._data = data

    def to_dict(self) -> dict:
        return dict(self._data)


def _session(tenant_id: str, role: str = "admin") -> SimpleNamespace:
    return SimpleNamespace(tenant_id=tenant_id, role=role, permissions=None, user_id="op-1")


def test_keep_surface_freeze_is_committed() -> None:
    from pathlib import Path

    text = Path("docs/KEEP_SURFACE.md").read_text(encoding="utf-8")
    assert "Live Chat" in text
    assert "DELETE candidates" in text
    assert "Luna" in text
    assert "Monty" in text
    assert "Creative" in text


def test_filter_chats_drops_foreign_and_unscoped_rows() -> None:
    payload = {
        "chats": [
            {"conversation_id": "a1", "tenant_id": "tenant-a", "user_id": "whatsapp:1", "channel": "whatsapp"},
            {"conversation_id": "b1", "tenant_id": "tenant-b", "user_id": "whatsapp:2", "channel": "whatsapp"},
            {"conversation_id": "x1", "user_id": "+96170111111", "channel": "whatsapp"},
        ]
    }
    out = filter_chats_for_session(_session("tenant-a"), payload)
    ids = [row["conversation_id"] for row in out["chats"]]
    assert ids == ["a1"]


def test_admin_channel_privilege_still_tenant_scoped() -> None:
    payload = {
        "chats": [
            {"conversation_id": "a-ig", "tenant_id": "tenant-a", "user_id": "instagram:1", "channel": "instagram"},
            {"conversation_id": "b-ig", "tenant_id": "tenant-b", "user_id": "instagram:2", "channel": "instagram"},
        ]
    }
    out = filter_chats_for_session(_session("tenant-a", role="admin"), payload)
    assert [row["conversation_id"] for row in out["chats"]] == ["a-ig"]


@pytest.mark.asyncio
async def test_unified_chats_tenant_a_never_sees_tenant_b(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from db.session import reset_engine_for_tests
    from services.persistence.chat_store import ChatTenantRequired, append_message

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/chat.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    svc = live_chat_service
    svc.invalidate_cache()
    append_message(
        user_id="whatsapp:aaa",
        role="user",
        text_body="from A",
        conversation_id="conv-a",
        metadata={"tenant_id": "tenant-a"},
    )
    append_message(
        user_id="whatsapp:bbb",
        role="user",
        text_body="from B",
        conversation_id="conv-b",
        metadata={"tenant_id": "tenant-b"},
    )
    with pytest.raises(ChatTenantRequired):
        append_message(user_id="+96170123456", role="user", text_body="no tenant", conversation_id="conv-unscoped")
    result_a = await svc.get_unified_chats(tenant_id="tenant-a", page=1, page_size=20, filter_state="all")
    result_b = await svc.get_unified_chats(tenant_id="tenant-b", page=1, page_size=20, filter_state="all")
    missing = await svc.get_unified_chats(search="", page=1, page_size=20, filter_state="all")
    reset_engine_for_tests()
    ids_a = [row["conversation_id"] for row in result_a.get("chats") or []]
    ids_b = [row["conversation_id"] for row in result_b.get("chats") or []]
    assert ids_a == ["conv-a"]
    assert ids_b == ["conv-b"]
    assert "conv-unscoped" not in ids_a
    assert missing.get("chats") == []
    assert missing.get("source") == "missing_tenant"


@pytest.mark.asyncio
async def test_unified_cache_does_not_leak_across_tenants(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from db.session import reset_engine_for_tests
    from services.persistence.chat_store import append_message

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/chat.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    svc = live_chat_service
    svc.invalidate_cache()
    append_message(
        user_id="whatsapp:aaa",
        role="user",
        text_body="cached",
        conversation_id="cached-a",
        metadata={"tenant_id": "tenant-a"},
    )
    leaked = await svc.get_unified_chats(tenant_id="tenant-b", page=1, page_size=20, filter_state="all")
    own = await svc.get_unified_chats(tenant_id="tenant-a", page=1, page_size=20, filter_state="all")
    reset_engine_for_tests()
    assert leaked.get("chats") == []
    assert [row["conversation_id"] for row in own.get("chats") or []] == ["cached-a"]


@pytest.mark.asyncio
async def test_conversation_details_reject_foreign_tenant(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from db.session import reset_engine_for_tests

    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/chat.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    svc = live_chat_service
    result = await svc.get_conversation_details(
        user_id="whatsapp:bbb",
        conversation_id="conv-b",
        tenant_id="tenant-a",
    )
    reset_engine_for_tests()
    assert result.get("success") is False
    assert result.get("error") == "Conversation not found"


@pytest.mark.asyncio
async def test_build_index_entry_requires_proven_tenant_for_upsert() -> None:
    svc = live_chat_service
    conv = {
        "conversation_id": "conv-ig",
        "customer_info": {"name": "Sara", "channel": "instagram"},
        "last_message_text": "hi",
        "last_message_at": utc_now(),
        "message_count": 1,
        "human_takeover_active": False,
    }
    entry = svc._build_index_entry("instagram:99", conv, [])
    assert entry["tenant_id"] == ""
    phone = svc._build_index_entry("+96170123456", {"conversation_id": "wa-1", "customer_info": {}}, [])
    assert phone.get("tenant_id") == ""
    with patch("services.live_chat.service_rebuild.get_document_db", return_value=MagicMock()):
        await svc._upsert_index_entry(phone)
