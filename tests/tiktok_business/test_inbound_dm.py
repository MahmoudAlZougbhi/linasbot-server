"""TikTok media-only DMs hydrate inbound media before Customer Brain."""

from __future__ import annotations

import pytest

from tests.tiktok_business.conftest import seed_connection


@pytest.mark.asyncio
async def test_media_only_dm_calls_brain(tt_db, monkeypatch) -> None:
    from services.tiktok_business.messaging import handle_messaging_webhook

    called: dict = {}

    async def fake_ai(snapshot):
        called["snapshot"] = snapshot

    async def fake_mirror(snapshot):
        called["mirrored"] = True

    monkeypatch.setattr("services.tiktok_business.messaging._maybe_ai_dm", fake_ai)
    monkeypatch.setattr("services.tiktok_business.messaging._mirror_live_chat", fake_mirror)
    seed_connection(
        tt_db,
        open_id="biz-dm",
        scopes=["user.info.basic", "message.list.read"],
    )
    result = await handle_messaging_webhook(
        payload={"user_openid": "biz-dm"},
        content={
            "conversation_id": "c1",
            "from": "cust-1",
            "message_id": "m-img",
            "message_type": "image",
        },
        event_name="im_receive_msg",
        event_id="evt-img",
    )
    assert result.get("gated") is False
    assert called["snapshot"]["text"] == ""
    assert called["snapshot"]["inbound_media"]["attachment_types"] == ["image"]
    assert called.get("mirrored") is True


@pytest.mark.asyncio
async def test_textless_untyped_dm_skips_brain(tt_db, monkeypatch) -> None:
    from services.tiktok_business.messaging import handle_messaging_webhook

    called = {"ai": False}

    async def fake_ai(snapshot):
        called["ai"] = True

    monkeypatch.setattr("services.tiktok_business.messaging._maybe_ai_dm", fake_ai)
    seed_connection(
        tt_db,
        open_id="biz-dm",
        scopes=["user.info.basic", "message.list.read"],
    )
    result = await handle_messaging_webhook(
        payload={"user_openid": "biz-dm"},
        content={"conversation_id": "c1", "from": "cust-1", "message_id": "m-empty"},
        event_name="im_receive_msg",
        event_id="evt-empty",
    )
    assert result.get("gated") is False
    assert called["ai"] is False
