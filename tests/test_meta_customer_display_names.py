"""Meta Instagram/Facebook customer display-name resolution."""

from __future__ import annotations

from typing import Any
from unittest import mock

import pytest

import config
from services import social_messaging_processor
from services.chat_response_service import _is_placeholder_booking_customer_name
from services.meta_messaging import (
    SOCIAL_DISPLAY_NAME_FALLBACK,
    MetaMessagingAdapter,
    MetaMessagingSettings,
    is_unresolved_social_display_name,
    normalize_social_display_name,
    parse_meta_messaging_events,
    pick_meta_participant_display_name,
    scrub_legacy_meta_channel_placeholder,
)


def _settings(**overrides: Any) -> MetaMessagingSettings:
    base = dict(
        enabled=True,
        app_secret="secret",
        page_id="378696005334409",
        page_access_token="page-token",
        instagram_account_id="17841413184256533",
        verify_token="verify",
        graph_api_version="v24.0",
        tenant_id="linas",
    )
    base.update(overrides)
    return MetaMessagingSettings(**base)


class TestMetaDisplayNameHelpers:
    def test_legacy_channel_placeholders_are_unresolved(self):
        assert is_unresolved_social_display_name("Instagram Customer")
        assert is_unresolved_social_display_name("Facebook Customer")
        assert is_unresolved_social_display_name("Customer")
        assert not is_unresolved_social_display_name("Sara Khalil")

    def test_pick_prefers_name_then_username(self):
        assert pick_meta_participant_display_name(name="Sara Khalil", username="sara_k") == "Sara Khalil"
        assert pick_meta_participant_display_name(username="sara_k") == "sara_k"
        assert pick_meta_participant_display_name(first_name="Sara", last_name="Khalil") == "Sara Khalil"
        assert pick_meta_participant_display_name(name="Instagram Customer") is None

    def test_scrub_only_legacy_channel_labels(self):
        assert scrub_legacy_meta_channel_placeholder("Instagram Customer") == SOCIAL_DISPLAY_NAME_FALLBACK
        assert scrub_legacy_meta_channel_placeholder("Facebook Customer") == SOCIAL_DISPLAY_NAME_FALLBACK
        assert scrub_legacy_meta_channel_placeholder("Unknown Customer") == "Unknown Customer"
        assert scrub_legacy_meta_channel_placeholder("Sara") == "Sara"

    def test_ai_placeholder_list_rejects_channel_labels(self):
        assert _is_placeholder_booking_customer_name("Instagram Customer")
        assert _is_placeholder_booking_customer_name("Facebook Customer")
        assert not _is_placeholder_booking_customer_name("Nour")


class TestMetaParseSenderLabels:
    def test_webhook_sender_name_and_username_forwarded(self):
        payload = {
            "object": "instagram",
            "entry": [
                {
                    "id": "IG_ACCOUNT",
                    "messaging": [
                        {
                            "sender": {"id": "IGSID1", "name": "Nour H.", "username": "nour_h"},
                            "recipient": {"id": "IG_ACCOUNT"},
                            "timestamp": 1,
                            "message": {"mid": "m-name", "text": "hi"},
                        }
                    ],
                }
            ],
        }
        events = parse_meta_messaging_events(payload, instagram_account_id="IG_ACCOUNT")
        assert len(events) == 1
        assert events[0]["sender_name"] == "Nour H."
        assert events[0]["sender_username"] == "nour_h"


@pytest.mark.asyncio
async def test_fetch_participant_profile_instagram_fields():
    client = mock.AsyncMock()
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"name": "Lina Client", "username": "lina_c"}
    client.get = mock.AsyncMock(return_value=response)
    adapter = MetaMessagingAdapter(
        access_token="token",
        account_id="page",
        channel="instagram",
        graph_api_version="v24.0",
        client=client,
    )
    profile = await adapter.fetch_participant_profile("IGSID99")
    assert profile["name"] == "Lina Client"
    assert profile["username"] == "lina_c"
    client.get.assert_awaited_once()
    _args, kwargs = client.get.await_args
    assert kwargs["params"]["fields"] == "name,username"


@pytest.mark.asyncio
async def test_fetch_participant_profile_facebook_fields():
    client = mock.AsyncMock()
    response = mock.Mock()
    response.status_code = 200
    response.json.return_value = {"name": "Omar Fares", "first_name": "Omar", "last_name": "Fares"}
    client.get = mock.AsyncMock(return_value=response)
    adapter = MetaMessagingAdapter(
        access_token="token",
        account_id="page",
        channel="facebook",
        graph_api_version="v24.0",
        client=client,
    )
    profile = await adapter.fetch_participant_profile("PSID99")
    assert pick_meta_participant_display_name(**{k: profile.get(k) for k in ("name", "first_name", "last_name", "username")}) == (
        "Omar Fares"
    )
    _args, kwargs = client.get.await_args
    assert kwargs["params"]["fields"] == "name,first_name,last_name"


@pytest.mark.asyncio
async def test_graph_name_replaces_legacy_placeholder(monkeypatch: pytest.MonkeyPatch):
    sender_id = "IGSID_REAL_NAME"
    user_id = f"instagram:{sender_id}"
    config.user_names[user_id] = "Instagram Customer"
    captured: dict[str, Any] = {}

    async def restore(_user_id: str) -> dict[str, Any]:
        return {"name": "Instagram Customer"}

    async def handle(**kwargs: Any) -> None:
        captured.update(kwargs)

    class _Adapter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def fetch_participant_profile(self, _pid: str) -> dict[str, Any]:
            return {"name": "Maya Haddad", "username": "maya_h"}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(social_messaging_processor, "get_user_state_from_firestore", restore)
    monkeypatch.setattr(social_messaging_processor, "handle_message", handle)
    monkeypatch.setattr(social_messaging_processor, "MetaMessagingAdapter", _Adapter)
    monkeypatch.setattr(social_messaging_processor, "save_user_name_to_firestore", mock.AsyncMock())

    try:
        await social_messaging_processor.process_meta_social_event(
            {
                "channel": "instagram",
                "sender_id": sender_id,
                "recipient_id": "17841413184256533",
                "account_id": "17841413184256533",
                "message_id": "mid-name-1",
                "text": "مرحبا",
            },
            _settings(),
            simulation=False,
        )
        assert captured["user_name"] == "Maya Haddad"
        assert captured["user_name"] != "Instagram Customer"
        assert not is_unresolved_social_display_name(captured["user_name"])
        assert config.user_names[user_id] == "Maya Haddad"
    finally:
        for mapping in (config.user_data_whatsapp, config.user_names, config.user_gender):
            mapping.pop(user_id, None)


@pytest.mark.asyncio
async def test_webhook_name_used_without_graph(monkeypatch: pytest.MonkeyPatch):
    sender_id = "PSID_WEBHOOK_NAME"
    user_id = f"facebook:{sender_id}"
    captured: dict[str, Any] = {}

    async def restore(_user_id: str) -> dict[str, Any]:
        return {}

    async def handle(**kwargs: Any) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(social_messaging_processor, "get_user_state_from_firestore", restore)
    monkeypatch.setattr(social_messaging_processor, "handle_message", handle)
    monkeypatch.setattr(social_messaging_processor, "save_user_name_to_firestore", mock.AsyncMock())

    try:
        await social_messaging_processor.process_meta_social_event(
            {
                "channel": "facebook",
                "sender_id": sender_id,
                "recipient_id": "378696005334409",
                "account_id": "378696005334409",
                "message_id": "mid-name-2",
                "text": "hello",
                "sender_name": "Rami Abboud",
            },
            _settings(),
            simulation=True,
        )
    finally:
        for mapping in (config.user_data_whatsapp, config.user_names, config.user_gender):
            mapping.pop(user_id, None)

    assert captured["user_name"] == "Rami Abboud"


@pytest.mark.asyncio
async def test_honest_fallback_when_graph_unavailable(monkeypatch: pytest.MonkeyPatch):
    sender_id = "IGSID_NO_PROFILE"
    user_id = f"instagram:{sender_id}"
    captured: dict[str, Any] = {}

    async def restore(_user_id: str) -> dict[str, Any]:
        return {}

    async def handle(**kwargs: Any) -> None:
        captured.update(kwargs)

    class _Adapter:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def fetch_participant_profile(self, _pid: str) -> dict[str, Any]:
            return {}

        async def close(self) -> None:
            return None

    monkeypatch.setattr(social_messaging_processor, "get_user_state_from_firestore", restore)
    monkeypatch.setattr(social_messaging_processor, "handle_message", handle)
    monkeypatch.setattr(social_messaging_processor, "MetaMessagingAdapter", _Adapter)

    try:
        await social_messaging_processor.process_meta_social_event(
            {
                "channel": "instagram",
                "sender_id": sender_id,
                "recipient_id": "17841413184256533",
                "account_id": "17841413184256533",
                "message_id": "mid-name-3",
                "text": "hi",
            },
            _settings(),
            simulation=False,
        )
    finally:
        for mapping in (config.user_data_whatsapp, config.user_names, config.user_gender):
            mapping.pop(user_id, None)

    assert captured["user_name"] == SOCIAL_DISPLAY_NAME_FALLBACK
    assert captured["user_name"] not in {"Instagram Customer", "Facebook Customer"}
    assert normalize_social_display_name(captured["user_name"]) == SOCIAL_DISPLAY_NAME_FALLBACK


@pytest.mark.asyncio
async def test_ai_name_is_known_false_for_legacy_placeholder(monkeypatch: pytest.MonkeyPatch):
    """Ensure AI context does not treat 'Instagram Customer' as a real greeting name."""
    from services import chat_response_service

    user_id = "instagram:IGSID_AI"
    config.user_names[user_id] = "Instagram Customer"
    config.user_data_whatsapp[user_id] = {
        "channel": "instagram",
        "phone_number": f"room:{user_id}",
        **config.DEFAULT_CONVERSATION_STATE,
    }

    # Replicate the name_is_known gate used before prompt construction.
    user_name = config.user_names.get(user_id, "client")
    placeholders = {
        "client",
        "unknown",
        "unknown customer",
        "instagram customer",
        "facebook customer",
        "customer",
        "test user",
    }
    name_is_known = (
        bool(user_name)
        and user_name != "client"
        and user_name.strip().lower() not in placeholders
        and not user_name.strip().lower().startswith("test user")
    )
    try:
        assert name_is_known is False
        assert _is_placeholder_booking_customer_name(user_name)
        # After Graph resolution, a real name becomes known.
        config.user_names[user_id] = "Maya Haddad"
        user_name = config.user_names[user_id]
        name_is_known = user_name.strip().lower() not in placeholders
        assert name_is_known is True
        assert chat_response_service._is_placeholder_booking_customer_name(user_name) is False
    finally:
        config.user_names.pop(user_id, None)
        config.user_data_whatsapp.pop(user_id, None)
