"""Comment inbox SSE payload + ACL. Never mixes comments onto WhatsApp DM threads."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from modules.live_chat_api_helpers import session_allows_live_chat_sse_event
from services.live_chat_channel import normalize_comment_inbox_channel
from services.live_chat_comment_sse import COMMENT_SSE_EVENT, comment_inbox_sse_payload, schedule_comment_inbox_sse
from services.live_chat_sse_broadcaster import live_chat_sse_broadcaster


def test_normalize_comment_inbox_channel() -> None:
    assert normalize_comment_inbox_channel("instagram_comment") == "instagram"
    assert normalize_comment_inbox_channel("facebook_comment") == "facebook"
    assert normalize_comment_inbox_channel("tiktok_comment") == "tiktok"
    assert normalize_comment_inbox_channel("whatsapp") is None
    assert normalize_comment_inbox_channel("web") is None


def test_comment_payload_requires_tenant_channel_and_comment_id() -> None:
    assert comment_inbox_sse_payload(tenant_id="", channel="instagram", comment_id="c1") is None
    assert comment_inbox_sse_payload(tenant_id="linas", channel="whatsapp", comment_id="c1") is None
    assert comment_inbox_sse_payload(tenant_id="linas", channel="instagram", comment_id="") is None
    body = comment_inbox_sse_payload(
        tenant_id="Linas",
        channel="instagram_comment",
        post_id="media1",
        comment_id="c1",
        author="sara",
        comment="price?",
        delivery_status="none",
    )
    assert body == {
        "tenant_id": "linas",
        "channel": "instagram",
        "platform": "instagram",
        "post_id": "media1",
        "comment_id": "c1",
        "author": "sara",
        "comment": "price?",
        "ai_reply": "",
        "delivery_status": "none",
    }


def test_comment_sse_acl() -> None:
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
    event = {"type": COMMENT_SSE_EVENT, "data": {"tenant_id": "linas", "channel": "instagram", "comment_id": "c1"}}
    assert session_allows_live_chat_sse_event(session, event)
    assert (
        session_allows_live_chat_sse_event(
            session,
            {"type": COMMENT_SSE_EVENT, "data": {"tenant_id": "linas", "channel": "facebook", "comment_id": "c1"}},
        )
        is False
    )
    assert (
        session_allows_live_chat_sse_event(
            session,
            {"type": COMMENT_SSE_EVENT, "data": {"tenant_id": "other", "channel": "instagram", "comment_id": "c1"}},
        )
        is False
    )
    assert (
        session_allows_live_chat_sse_event(
            session,
            {"type": COMMENT_SSE_EVENT, "data": {"tenant_id": "linas", "comment_id": "c1"}},
        )
        is False
    )


@pytest.mark.asyncio
async def test_comment_broadcast_uses_comment_update_event(monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[tuple[str, dict]] = []

    async def fake_publish(event_type: str, data: dict) -> None:
        published.append((event_type, data))

    monkeypatch.setattr(live_chat_sse_broadcaster, "publish", fake_publish)
    monkeypatch.setattr(live_chat_sse_broadcaster, "active_clients_count", AsyncMock(return_value=0))

    from modules.live_chat_api_helpers import broadcast_sse_event

    await broadcast_sse_event(
        COMMENT_SSE_EVENT,
        {"tenant_id": "linas", "channel": "instagram", "comment_id": "c1", "post_id": "p1"},
    )
    assert published[0][0] == COMMENT_SSE_EVENT
    assert published[0][1]["comment_id"] == "c1"
    assert published[0][1]["channel"] == "instagram"


def test_schedule_without_running_loop_is_noop() -> None:
    schedule_comment_inbox_sse(tenant_id="linas", channel="instagram", comment_id="c1", comment="hi")
