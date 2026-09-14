"""Live Chat tenant identity: fail-closed, no unprefixed linas inference."""

from __future__ import annotations

from services.live_chat.channel import live_chat_event_tenant_id
from services.live_chat.tenant import (
    conversation_tenant_fields,
    resolve_live_chat_tenant_id,
    row_belongs_to_tenant,
)


def test_prefixed_social_ids_carry_tenant() -> None:
    assert resolve_live_chat_tenant_id(user_id="acme:instagram:ig:psid") == "acme"
    assert resolve_live_chat_tenant_id(user_id="shop:tiktok:open:id") == "shop"
    assert resolve_live_chat_tenant_id(conversation_id="web:shop-b:visitor-1") == "shop-b"


def test_unprefixed_meta_ids_are_unscoped() -> None:
    assert resolve_live_chat_tenant_id(user_id="instagram:178414") == ""
    assert resolve_live_chat_tenant_id(user_id="facebook:page:user") == ""
    assert resolve_live_chat_tenant_id(user_id="tiktok:open_id") == ""


def test_phone_and_web_user_ids_do_not_invent_linas() -> None:
    assert resolve_live_chat_tenant_id(user_id="+96170123456") == ""
    assert resolve_live_chat_tenant_id(user_id="whatsapp:+96170123456") == ""
    assert resolve_live_chat_tenant_id(user_id="web:visitor-1") == ""
    assert live_chat_event_tenant_id("+96170123456") == ""
    assert live_chat_event_tenant_id("web:visitor-1") == ""


def test_payload_tenant_wins_and_missing_is_unscoped() -> None:
    assert (
        resolve_live_chat_tenant_id(
            user_id="+96170123456",
            payload={"tenant_id": "linas"},
        )
        == "linas"
    )
    assert row_belongs_to_tenant({"tenant_id": "a", "user_id": "+1"}, "a") is True
    assert row_belongs_to_tenant({"tenant_id": "a", "user_id": "+1"}, "b") is False
    assert row_belongs_to_tenant({"user_id": "+96170123456"}, "linas") is False


def test_conversation_tenant_fields_fail_closed() -> None:
    assert conversation_tenant_fields(user_id="+96170") == {}
    assert conversation_tenant_fields(user_id="instagram:99", customer_info={"name": "Sara"}) == {}
    out = conversation_tenant_fields(user_id="shop:instagram:ig:99", customer_info={"name": "Sara"})
    assert out["tenant_id"] == "shop"
    assert out["customer_info"]["tenant_id"] == "shop"
