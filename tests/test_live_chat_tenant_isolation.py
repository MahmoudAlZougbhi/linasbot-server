"""HIGH: tenant A never sees tenant B Live Chat threads."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.access_channels import filter_chats_for_session
from services.live_chat_contracts import utc_now
from services.live_chat_service import live_chat_service


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
async def test_unified_chats_tenant_a_never_sees_tenant_b() -> None:
    svc = live_chat_service
    svc.invalidate_cache()
    now = utc_now()
    docs = [
        _Doc(
            "conv-a",
            {
                "tenant_id": "tenant-a",
                "user_id": "whatsapp:aaa",
                "last_message_text": "from A",
                "last_message_at": now,
                "conversation_state": svc.STATE_BOT_ACTIVE,
                "human_takeover_active": False,
            },
        ),
        _Doc(
            "conv-b",
            {
                "tenant_id": "tenant-b",
                "user_id": "whatsapp:bbb",
                "last_message_text": "from B",
                "last_message_at": now,
                "conversation_state": svc.STATE_BOT_ACTIVE,
                "human_takeover_active": False,
            },
        ),
        _Doc(
            "conv-unscoped",
            {
                "user_id": "+96170123456",
                "last_message_text": "no tenant",
                "last_message_at": now,
                "conversation_state": svc.STATE_BOT_ACTIVE,
                "human_takeover_active": False,
            },
        ),
    ]
    with (
        patch("services.live_chat_service_unified.get_firestore_db", return_value=MagicMock()),
        patch.object(svc, "_index_collection", return_value=MagicMock()),
        patch.object(svc, "_run_blocking_with_timeout", new_callable=AsyncMock, return_value=docs),
        patch.object(svc, "_compute_index_counters", new_callable=AsyncMock, return_value=svc._empty_counters()),
        patch.object(svc, "_stream_tenant_index_docs", return_value=docs),
    ):
        result_a = await svc.get_unified_chats(tenant_id="tenant-a", page=1, page_size=20, filter_state="all")
        result_b = await svc.get_unified_chats(tenant_id="tenant-b", page=1, page_size=20, filter_state="all")
        missing = await svc.get_unified_chats(search="", page=1, page_size=20, filter_state="all")
    ids_a = [row["conversation_id"] for row in result_a.get("chats") or []]
    ids_b = [row["conversation_id"] for row in result_b.get("chats") or []]
    assert ids_a == ["conv-a"]
    assert ids_b == ["conv-b"]
    assert "conv-unscoped" not in ids_a
    assert "conv-unscoped" not in ids_b
    assert missing.get("chats") == []
    assert missing.get("source") == "missing_tenant"


@pytest.mark.asyncio
async def test_unified_cache_does_not_leak_across_tenants() -> None:
    svc = live_chat_service
    svc.invalidate_cache()
    svc._store_unified_inbox(
        "tenant-a",
        chats=[
            {
                "conversation_id": "cached-a",
                "tenant_id": "tenant-a",
                "user_id": "whatsapp:aaa",
                "last_message_at": utc_now().isoformat(),
                "conversation_state": svc.STATE_BOT_ACTIVE,
            }
        ],
        has_more=False,
        total=1,
        next_cursor=None,
        page_size=20,
        counters=svc._empty_counters(),
    )
    with patch("services.live_chat_service_unified.get_firestore_db", return_value=None):
        leaked = await svc.get_unified_chats(tenant_id="tenant-b", page=1, page_size=20, filter_state="all")
        own = await svc.get_unified_chats(tenant_id="tenant-a", page=1, page_size=20, filter_state="all")
    assert leaked.get("chats") == []
    assert [row["conversation_id"] for row in own.get("chats") or []] == ["cached-a"]


@pytest.mark.asyncio
async def test_conversation_details_reject_foreign_tenant() -> None:
    svc = live_chat_service
    with (
        patch("services.live_chat_service_details.get_firestore_db", return_value=MagicMock()),
        patch.object(svc, "thread_visible_to_tenant", new_callable=AsyncMock, return_value=False),
    ):
        result = await svc.get_conversation_details(
            user_id="whatsapp:bbb",
            conversation_id="conv-b",
            tenant_id="tenant-a",
        )
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
    assert entry["tenant_id"] == "linas"
    phone = svc._build_index_entry("+96170123456", {"conversation_id": "wa-1", "customer_info": {}}, [])
    assert phone.get("tenant_id") == ""
    with patch("services.live_chat_service_rebuild.get_firestore_db", return_value=MagicMock()):
        await svc._upsert_index_entry(phone)
