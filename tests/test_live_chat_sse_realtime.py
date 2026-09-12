"""Live Chat SSE: HA Redis fanout, tenant/channel filter, authenticated stream path."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.routing import APIRoute

from modules.live_chat_api_helpers import broadcast_sse_event, session_allows_live_chat_sse_event
from services.live_chat_channel import live_chat_event_tenant_id
from services.live_chat_sse_broadcaster import live_chat_sse_broadcaster


def test_live_chat_api_and_sse_modules_under_500_lines() -> None:
    for rel in (
        "modules/live_chat_api.py",
        "modules/live_chat_api_helpers.py",
        "services/live_chat_sse_broadcaster.py",
        "services/live_chat_channel.py",
    ):
        assert len(Path(rel).read_text(encoding="utf-8").splitlines()) < 500, rel


def test_live_chat_events_route_is_registered() -> None:
    import modules.live_chat_api  # noqa: F401
    from modules.core import app

    routes = [route for route in app.routes if isinstance(route, APIRoute) and route.path == "/api/live-chat/events"]
    assert routes
    assert "GET" in (routes[0].methods or set())


def test_live_chat_events_requires_auth() -> None:
    from fastapi.testclient import TestClient

    import modules.live_chat_api  # noqa: F401
    from modules.core import app

    client = TestClient(app)
    response = client.get("/api/live-chat/events")
    assert response.status_code == 401


def test_live_chat_event_tenant_id_from_prefixed_social_ids() -> None:
    assert live_chat_event_tenant_id("acme:instagram:ig:psid") == "acme"
    assert live_chat_event_tenant_id("linas:facebook:page:user") == "linas"
    assert live_chat_event_tenant_id("shop:tiktok:open:id") == "shop"
    assert live_chat_event_tenant_id("+96170123456") == "linas"
    assert live_chat_event_tenant_id("tiktok:open_id") == "linas"
    assert live_chat_event_tenant_id("instagram:178414") == "linas"


def _event(event_type: str, data: dict) -> dict:
    return {"type": event_type, "data": data}


def test_sse_filter_allows_heartbeat_and_connected() -> None:
    session = SimpleNamespace(tenant_id="linas", role="admin", permissions=None)
    assert session_allows_live_chat_sse_event(session, _event("heartbeat", {}))
    assert session_allows_live_chat_sse_event(session, _event("connected", {}))


def test_sse_filter_drops_missing_or_mismatched_tenant() -> None:
    session = SimpleNamespace(tenant_id="linas", role="admin", permissions=None)
    assert session_allows_live_chat_sse_event(session, {"type": "new_message", "data": None}) is False
    assert session_allows_live_chat_sse_event(session, _event("new_message", {})) is False
    assert (
        session_allows_live_chat_sse_event(
            session,
            _event("new_message", {"tenant_id": "other", "user_id": "+96170123456"}),
        )
        is False
    )
    empty = SimpleNamespace(tenant_id="", role="admin", permissions=None)
    assert (
        session_allows_live_chat_sse_event(
            empty,
            _event("new_message", {"tenant_id": "linas", "user_id": "+96170123456"}),
        )
        is False
    )


def test_sse_filter_allows_same_tenant_whatsapp_and_conversations() -> None:
    session = SimpleNamespace(tenant_id="linas", role="admin", permissions=None)
    assert session_allows_live_chat_sse_event(
        session,
        _event("new_message", {"tenant_id": "linas", "user_id": "+96170123456"}),
    )
    assert session_allows_live_chat_sse_event(
        session,
        _event("conversations", {"tenant_id": "linas", "trigger_refresh": True}),
    )
    assert session_allows_live_chat_sse_event(
        session,
        _event("message_status", {"tenant_id": "linas", "user_id": "+96170123456", "delivery_status": "sent"}),
    )
    assert session_allows_live_chat_sse_event(
        session,
        _event("comment_update", {"tenant_id": "linas", "channel": "instagram", "comment_id": "c1"}),
    )


def test_sse_filter_channel_acl_fail_closed() -> None:
    session = SimpleNamespace(
        tenant_id="linas",
        role="operator",
        permissions={
            "channelWhatsapp": False,
            "channelInstagram": True,
            "channelFacebook": False,
            "channelTiktok": False,
            "channelWeb": False,
        },
    )
    assert session_allows_live_chat_sse_event(
        session,
        _event("new_message", {"tenant_id": "linas", "user_id": "instagram:1"}),
    )
    assert (
        session_allows_live_chat_sse_event(
            session,
            _event("new_message", {"tenant_id": "linas", "user_id": "+96170123456"}),
        )
        is False
    )
    assert (
        session_allows_live_chat_sse_event(
            session,
            _event("message_status", {"tenant_id": "linas", "user_id": "+96170123456"}),
        )
        is False
    )


@pytest.mark.asyncio
async def test_broadcast_publishes_when_no_local_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[tuple[str, dict]] = []

    async def fake_publish(event_type: str, data: dict) -> None:
        published.append((event_type, data))

    monkeypatch.setattr(live_chat_sse_broadcaster, "publish", fake_publish)
    monkeypatch.setattr(live_chat_sse_broadcaster, "active_clients_count", AsyncMock(return_value=0))

    await broadcast_sse_event("new_message", {"user_id": "+96170123456", "conversation_id": "c1"})
    assert published[0][0] == "new_message"
    body = published[0][1]
    assert body["user_id"] == "+96170123456"
    assert body["conversation_id"] == "c1"
    assert body["tenant_id"] == "linas"
    assert body["channel"] == "whatsapp"
    assert body["event_id"]
    assert body["event_ts"]

    published.clear()
    await broadcast_sse_event(
        "new_message",
        {"user_id": "shop:instagram:ig:psid", "conversation_id": "c2"},
    )
    assert published[0][1]["tenant_id"] == "shop"
    assert published[0][1]["channel"] == "instagram"


def test_sse_new_message_payload_includes_inbox_preview_fields() -> None:
    from utils.utils_conversation_save_common import _sse_new_message_payload

    payload = _sse_new_message_payload(
        canonical_user_id="+96170123456",
        conversation_id="conv-1",
        role="user",
        text="كم السعر؟",
        customer_info={"name": "Sara", "phone_full": "+96170123456"},
        message_data={"role": "user", "text": "كم السعر؟", "message_id": "m1"},
        unread_count=2,
    )
    assert payload["user_id"] == "+96170123456"
    assert payload["conversation_id"] == "conv-1"
    assert payload["user_name"] == "Sara"
    assert payload["text"] == "كم السعر؟"
    assert payload["unread_count"] == 2
    assert payload["message"]["is_user"] is True
    assert payload["message"]["content"] == "كم السعر؟"
