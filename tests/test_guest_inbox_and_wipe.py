"""Guest threads stay on one tenant, and the wipe SQL leaves accounts alone."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from scripts.wipe_live_chat_history import chat_delete_statements
from services.guest.guest_chat_store import GuestMessage, GuestSession
from services.guest.guest_inbox_bridge import publish_guest_view


def test_wipe_statements_target_chats_only() -> None:
    sql = "\n".join(chat_delete_statements()).lower()
    assert "linas_chat_threads" in sql
    assert "linas_chat_messages" in sql
    assert "live_chat_index" in sql
    assert "dashboard_users" not in sql
    assert "dashboard_sessions" not in sql
    assert "linas_inbound_events" not in sql
    assert "web_chat_widgets" not in sql


def test_guest_projection_is_tenant_scoped(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from db.session import reset_engine_for_tests
    from services.persistence.chat_store import list_inbox

    monkeypatch.setenv("LINAS_GUEST_INBOX", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/guest.sqlite")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    monkeypatch.setattr(
        "services.guest.guest_inbox_bridge.resolve_guest_widget",
        lambda _origin: SimpleNamespace(tenant_id="tenant-a", widget_key="widget-a", site_url=""),
    )
    monkeypatch.setattr("services.guest.guest_inbox_bridge._ensure_visitor", lambda *_a, **_k: None)
    session = GuestSession(
        id="guest-session-a1",
        created_at=1.0,
        updated_at=1.0,
        messages=[GuestMessage(id="m1", role="user", content="hello", created_at=1.0)],
    )
    view = publish_guest_view(session, origin="https://shop.example")
    reset_engine_for_tests()
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", f"sqlite:///{tmp_path}/guest.sqlite")
    inbox_a = list_inbox("tenant-a", limit=20)
    inbox_b = list_inbox("tenant-b", limit=20)
    reset_engine_for_tests()
    assert view["live_token"]
    assert [row["conversation_id"] for row in inbox_a["threads"]] == ["web:tenant-a:guest-session-a1"]
    assert inbox_b["threads"] == []
