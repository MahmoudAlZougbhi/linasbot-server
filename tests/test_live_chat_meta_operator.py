from __future__ import annotations

from services.live_chat_meta_operator import (
    is_meta_dm_live_chat_user,
    parse_meta_live_chat_user_id,
)


def test_parse_linas_single_asset_meta_user_id() -> None:
    channel, sender, asset, tenant = parse_meta_live_chat_user_id("instagram:1761620091644326")
    assert channel == "instagram"
    assert sender == "1761620091644326"
    assert asset is None
    assert tenant is None


def test_parse_linas_multi_asset_meta_user_id() -> None:
    channel, sender, asset, tenant = parse_meta_live_chat_user_id("facebook:378696005334409:27900569179577939")
    assert channel == "facebook"
    assert sender == "27900569179577939"
    assert asset == "378696005334409"
    assert tenant is None


def test_is_meta_dm_live_chat_user() -> None:
    assert is_meta_dm_live_chat_user("instagram:1")
    assert is_meta_dm_live_chat_user("facebook:2")
    assert not is_meta_dm_live_chat_user("+96170000000")
    assert not is_meta_dm_live_chat_user("tiktok:abc:1")
