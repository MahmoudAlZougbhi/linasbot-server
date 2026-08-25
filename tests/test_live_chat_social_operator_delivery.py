from __future__ import annotations

import pytest

from services.live_chat_meta_operator_media import decode_operator_media_payload
from services.live_chat_operator_social_delivery import is_social_live_chat_user
from services.live_chat_tiktok_operator import (
    parse_tiktok_live_chat_user_id,
    tiktok_operator_media_not_supported,
)


def test_decode_operator_media_payload() -> None:
    import base64

    raw = base64.b64encode(b"hello").decode()
    assert decode_operator_media_payload(raw) == b"hello"
    assert decode_operator_media_payload(f"data:image/jpeg;base64,{raw}") == b"hello"


def test_parse_tiktok_live_chat_user_id() -> None:
    sender, conn, tenant = parse_tiktok_live_chat_user_id("tiktok:cust-1")
    assert sender == "cust-1"
    assert conn is None
    assert tenant is None

    sender, conn, tenant = parse_tiktok_live_chat_user_id("tiktok:conn-1:cust-9")
    assert sender == "cust-9"
    assert conn == "conn-1"

    sender, conn, tenant = parse_tiktok_live_chat_user_id("shop-1:tiktok:conn-1:cust-9")
    assert sender == "cust-9"
    assert conn == "conn-1"
    assert tenant == "shop-1"


def test_is_social_live_chat_user() -> None:
    assert is_social_live_chat_user("instagram:1")
    assert is_social_live_chat_user("tiktok:abc")
    assert not is_social_live_chat_user("+96170000000")


def test_tiktok_operator_media_not_supported() -> None:
    result = tiktok_operator_media_not_supported()
    assert result["success"] is False
    assert "not supported" in result["error"].lower()


@pytest.mark.asyncio
async def test_deliver_tiktok_operator_text_missing_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.live_chat_tiktok_operator import deliver_live_chat_tiktok_operator_text

    class FakeRepo:
        def get_connection(self, connection_id: str, *, tenant_id: str | None = None):
            return None

        def get_active_for_tenant(self, tenant_id: str):
            return None

    class FakeCtx:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("services.live_chat_tiktok_operator.whatsapp_session", lambda: FakeCtx())
    monkeypatch.setattr("services.live_chat_tiktok_operator.TikTokRepository", lambda session: FakeRepo())

    result = await deliver_live_chat_tiktok_operator_text(
        tenant_id="linas",
        user_id="tiktok:cust-1",
        conversation_id="conv-1",
        text="hello",
    )
    assert result["success"] is False
    assert result["error"] == "tiktok_connection_not_found"
