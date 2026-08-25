from __future__ import annotations

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
