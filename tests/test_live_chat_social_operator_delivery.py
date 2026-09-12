from __future__ import annotations

from services.live_chat_meta_operator_media import decode_operator_media_payload
from services.live_chat_operator_social_delivery import (
    infer_live_chat_source_channel,
    is_social_live_chat_user,
    live_chat_needs_whatsapp_session,
)
from services.live_chat_tiktok_operator import (
    parse_tiktok_live_chat_user_id,
    tiktok_operator_media_not_supported,
)
from services.requests.constants import (
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
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


def test_infer_live_chat_source_channel() -> None:
    assert infer_live_chat_source_channel("instagram:1761") == SOURCE_CHANNEL_INSTAGRAM_DM
    assert infer_live_chat_source_channel("facebook:page:user") == SOURCE_CHANNEL_FACEBOOK_MESSENGER
    assert infer_live_chat_source_channel("tiktok:cust") == "tiktok"
    assert infer_live_chat_source_channel("+96170123456") is None
    assert infer_live_chat_source_channel("instagram:1", SOURCE_CHANNEL_WHATSAPP_CLOUD) == SOURCE_CHANNEL_WHATSAPP_CLOUD


def test_live_chat_needs_whatsapp_session() -> None:
    assert live_chat_needs_whatsapp_session(user_id="instagram:1", tenant_id="linas", source_channel=None) is False
    assert live_chat_needs_whatsapp_session(user_id="facebook:p:u", tenant_id="linas", source_channel=None) is False
    assert live_chat_needs_whatsapp_session(user_id="tiktok:c", tenant_id="linas", source_channel=None) is False
    assert live_chat_needs_whatsapp_session(user_id="+96170123456", tenant_id="linas", source_channel=None) is True
    assert live_chat_needs_whatsapp_session(user_id="instagram:1", tenant_id=None, source_channel=None) is False


def test_tiktok_operator_media_not_supported() -> None:
    result = tiktok_operator_media_not_supported()
    assert result["success"] is False
    assert "not supported" in result["error"].lower()
