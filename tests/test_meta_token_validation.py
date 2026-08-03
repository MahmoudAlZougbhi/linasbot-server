"""Strict allowlist tests for new-app Page token metadata."""

import pytest

from scripts.validate_meta_social_token import (
    MetaTokenValidationError,
    validate_app_webhook_payload,
    validate_conversation_payloads,
    validate_instagram_subscription_payload,
    validate_page_subscription_payload,
    validate_payloads,
)


def _valid_payloads() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        {
            "data": {
                "is_valid": True,
                "app_id": "999000111222333",
                "type": "PAGE",
                "expires_at": 0,
                "scopes": [
                    "pages_messaging",
                    "pages_manage_metadata",
                    "pages_show_list",
                    "pages_read_engagement",
                    "instagram_basic",
                    "instagram_manage_messages",
                ],
                "granular_scopes": [
                    {
                        "scope": "pages_messaging",
                        "target_ids": ["378696005334409"],
                    },
                    {
                        "scope": "instagram_manage_messages",
                        "target_ids": ["17841413184256533"],
                    },
                ],
            }
        },
        {"id": "378696005334409"},
        {
            "id": "378696005334409",
            "instagram_business_account": {"id": "17841413184256533"},
        },
    )


def test_exact_page_instagram_app_scopes_and_targets_pass() -> None:
    debug, profile, page = _valid_payloads()
    checks = validate_payloads(debug, profile, page, expected_app_id="999000111222333")
    assert all(checks.values())


@pytest.mark.parametrize(
    "failure",
    ["old_app", "wrong_page", "wrong_instagram", "extra_target", "missing_scope", "expiring_token"],
)
def test_unexpected_token_identity_or_access_fails(failure: str) -> None:
    debug, profile, page = _valid_payloads()
    app_id = "999000111222333"
    if failure == "old_app":
        app_id = "1784792718776344"
    elif failure == "wrong_page":
        profile["id"] = "999999999999999"
    elif failure == "wrong_instagram":
        page["instagram_business_account"] = {"id": "99999999999999999"}
    elif failure == "extra_target":
        data = debug["data"]
        assert isinstance(data, dict)
        granular = data["granular_scopes"]
        assert isinstance(granular, list)
        granular.append({"scope": "pages_messaging", "target_ids": ["999999999999999"]})
    elif failure == "expiring_token":
        data = debug["data"]
        assert isinstance(data, dict)
        data["expires_at"] = 1_800_000_000
    else:
        data = debug["data"]
        assert isinstance(data, dict)
        scopes = data["scopes"]
        assert isinstance(scopes, list)
        scopes.remove("pages_messaging")

    with pytest.raises(MetaTokenValidationError):
        validate_payloads(debug, profile, page, expected_app_id=app_id)


def test_messenger_and_instagram_conversation_queries_accept_empty_data() -> None:
    checks = validate_conversation_payloads({"data": []}, {"data": []})

    assert checks == {
        "messenger_conversations_query_succeeded": True,
        "instagram_conversations_query_succeeded": True,
    }


@pytest.mark.parametrize("channel", ["messenger", "instagram"])
def test_malformed_conversation_query_payload_fails_closed(channel: str) -> None:
    messenger: dict[str, object] = {"data": []}
    instagram: dict[str, object] = {"data": []}
    if channel == "messenger":
        messenger = {"error": {"message": "not rendered"}}
    else:
        instagram = {"error": {"message": "not rendered"}}

    with pytest.raises(MetaTokenValidationError):
        validate_conversation_payloads(messenger, instagram)


def test_exact_dm_only_page_subscription_passes() -> None:
    checks = validate_page_subscription_payload(
        {
            "data": [
                {
                    "id": "999000111222333",
                    "subscribed_fields": ["messages", "messaging_postbacks"],
                }
            ]
        },
        expected_app_id="999000111222333",
    )

    assert all(checks.values())


@pytest.mark.parametrize("failure", ["none", "multiple", "wrong_app", "extra_field", "missing_field"])
def test_page_subscription_mismatch_fails_closed(failure: str) -> None:
    app = {
        "id": "999000111222333",
        "subscribed_fields": ["messages", "messaging_postbacks"],
    }
    data: list[dict[str, object]] = [app]
    if failure == "none":
        data = []
    elif failure == "multiple":
        data.append({"id": "another-app", "subscribed_fields": ["messages"]})
    elif failure == "wrong_app":
        app["id"] = "1784792718776344"
    elif failure == "extra_field":
        app["subscribed_fields"] = ["messages", "messaging_postbacks", "feed"]
    else:
        app["subscribed_fields"] = ["messages"]

    with pytest.raises(MetaTokenValidationError):
        validate_page_subscription_payload(
            {"data": data},
            expected_app_id="999000111222333",
        )


def test_exact_dm_only_instagram_subscription_passes() -> None:
    checks = validate_instagram_subscription_payload(
        {
            "data": [
                {
                    "id": "999000111222333",
                    "subscribed_fields": ["messaging_postbacks", "messages"],
                }
            ]
        },
        expected_app_id="999000111222333",
    )

    assert all(checks.values())


def test_exact_page_and_instagram_app_webhooks_pass() -> None:
    fields = [{"name": "messages"}, {"name": "messaging_postbacks"}]
    checks = validate_app_webhook_payload(
        {
            "data": [
                {
                    "object": "page",
                    "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                    "active": True,
                    "fields": fields,
                },
                {
                    "object": "instagram",
                    "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                    "active": True,
                    "fields": fields,
                },
            ]
        }
    )

    assert all(checks.values())


@pytest.mark.parametrize(
    "failure",
    ["missing_instagram", "inactive_page", "wrong_callback", "extra_object", "extra_field"],
)
def test_app_webhook_mismatch_fails_closed(failure: str) -> None:
    fields: list[object] = [{"name": "messages"}, {"name": "messaging_postbacks"}]
    page: dict[str, object] = {
        "object": "page",
        "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
        "active": True,
        "fields": fields,
    }
    instagram: dict[str, object] = {
        "object": "instagram",
        "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
        "active": True,
        "fields": fields,
    }
    data = [page, instagram]
    if failure == "missing_instagram":
        data = [page]
    elif failure == "inactive_page":
        page["active"] = False
    elif failure == "wrong_callback":
        instagram["callback_url"] = "https://example.invalid/webhook"
    elif failure == "extra_object":
        data.append({"object": "feed", "active": True, "fields": []})
    else:
        instagram["fields"] = [*fields, {"name": "comments"}]

    with pytest.raises(MetaTokenValidationError):
        validate_app_webhook_payload({"data": data})
