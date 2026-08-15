"""Strict allowlist tests for Meta token validation contract sections."""

from __future__ import annotations

import pytest

from scripts.meta_webhook_contract import (
    APP_INSTAGRAM_WEBHOOK_FIELDS,
    APP_PAGE_WEBHOOK_FIELDS,
    COMMENT_FEATURE_SCOPES,
    DM_WEBHOOK_FIELDS,
    PAGE_SUBSCRIPTION_COMMENT_DELIVERY,
    PUBLISH_FEATURE_SCOPES,
    evaluate_feature_readiness,
)
from scripts.validate_meta_social_token import (
    MetaTokenValidationError,
    validate_app_webhook_configuration,
    validate_conversation_payloads,
    validate_page_subscription_baseline,
    validate_page_subscription_configuration,
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
                ],
                "granular_scopes": [
                    {
                        "scope": "pages_messaging",
                        "target_ids": ["378696005334409"],
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


def _page_subscription_payload(*, fields: set[str], app_id: str = "999000111222333") -> dict[str, object]:
    return {
        "data": [
            {
                "id": app_id,
                "subscribed_fields": sorted(fields),
            }
        ]
    }


def _app_webhook_payload(
    *,
    page_fields: list[str] | None = None,
    instagram_fields: list[str] | None = None,
) -> dict[str, object]:
    return {
        "data": [
            {
                "object": "page",
                "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                "active": True,
                "fields": [{"name": field} for field in (page_fields or sorted(APP_PAGE_WEBHOOK_FIELDS))],
            },
            {
                "object": "instagram",
                "callback_url": "https://www.linasaibot.com/webhook/instagram-login",
                "active": True,
                "fields": [{"name": field} for field in (instagram_fields or sorted(APP_INSTAGRAM_WEBHOOK_FIELDS))],
            },
        ]
    }


def test_page_only_app_scopes_and_target_pass() -> None:
    debug, profile, page = _valid_payloads()
    checks = validate_payloads(debug, profile, page, expected_app_id="999000111222333")
    assert all(checks.values())


@pytest.mark.parametrize(
    "failure",
    ["old_app", "wrong_page", "wrong_instagram", "missing_target", "missing_scope", "expiring_token"],
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
    elif failure == "missing_target":
        data = debug["data"]
        assert isinstance(data, dict)
        granular = data["granular_scopes"]
        assert isinstance(granular, list)
        first = granular[0]
        assert isinstance(first, dict)
        first["target_ids"] = ["999999999999999"]
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


def test_additional_explicit_page_targets_do_not_invalidate_token() -> None:
    debug, profile, page = _valid_payloads()
    data = debug["data"]
    assert isinstance(data, dict)
    granular = data["granular_scopes"]
    assert isinstance(granular, list)
    first = granular[0]
    assert isinstance(first, dict)
    targets = first["target_ids"]
    assert isinstance(targets, list)
    targets.append("999999999999999")

    checks = validate_payloads(debug, profile, page, expected_app_id="999000111222333")

    assert checks["granular_targets_present"] is True


def test_messenger_and_explicit_legacy_instagram_queries_accept_empty_data() -> None:
    checks = validate_conversation_payloads({"data": []}, {"data": []})

    assert checks == {
        "messenger_conversations_query_succeeded": True,
        "legacy_instagram_conversations_query_succeeded": True,
    }


def test_current_app_a_conversation_probe_is_facebook_only() -> None:
    assert validate_conversation_payloads({"data": []}) == {
        "messenger_conversations_query_succeeded": True,
    }


@pytest.mark.parametrize("channel", ["messenger", "legacy_instagram"])
def test_malformed_conversation_query_payload_fails_closed(channel: str) -> None:
    messenger: dict[str, object] = {"data": []}
    instagram: dict[str, object] = {"data": []}
    if channel == "messenger":
        messenger = {"error": {"message": "not rendered"}}
    else:
        instagram = {"error": {"message": "not rendered"}}

    with pytest.raises(MetaTokenValidationError):
        validate_conversation_payloads(messenger, instagram)


def test_exact_dm_only_page_subscription_baseline_passes() -> None:
    payload = _page_subscription_payload(fields=DM_WEBHOOK_FIELDS)
    checks = validate_page_subscription_baseline(payload, expected_app_id="999000111222333")
    config = validate_page_subscription_configuration(
        payload,
        expected_app_id="999000111222333",
        expect_facebook_comment_delivery=False,
    )

    assert checks["page_subscribed_dm_fields_present"] is True
    assert config["facebook_comment_delivery_infrastructure_ready"] is False
    assert config["facebook_comment_delivery_profile_matches_expectation"] is True


def test_page_feed_plus_dm_baseline_passes_and_delivery_ready() -> None:
    payload = _page_subscription_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY)
    checks = validate_page_subscription_baseline(payload, expected_app_id="999000111222333")
    config = validate_page_subscription_configuration(
        payload,
        expected_app_id="999000111222333",
        expect_facebook_comment_delivery=True,
    )

    assert checks["page_subscribed_dm_fields_present"] is True
    assert config["facebook_comment_delivery_infrastructure_ready"] is True


def test_page_subscription_payload_alias_uses_baseline_only() -> None:
    checks = validate_page_subscription_payload(
        _page_subscription_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        expected_app_id="999000111222333",
    )
    assert checks["page_subscribed_dm_fields_present"] is True


@pytest.mark.parametrize("failure", ["none", "multiple", "wrong_app", "missing_field"])
def test_page_subscription_baseline_mismatch_fails_closed(failure: str) -> None:
    app = {
        "id": "999000111222333",
        "subscribed_fields": sorted(DM_WEBHOOK_FIELDS),
    }
    data: list[dict[str, object]] = [app]
    if failure == "none":
        data = []
    elif failure == "multiple":
        data.append({"id": "another-app", "subscribed_fields": ["messages"]})
    elif failure == "wrong_app":
        app["id"] = "1784792718776344"
    else:
        app["subscribed_fields"] = ["messages"]

    with pytest.raises(MetaTokenValidationError):
        validate_page_subscription_baseline({"data": data}, expected_app_id="999000111222333")


def test_page_subscription_extra_field_fails_configuration_not_baseline() -> None:
    payload = _page_subscription_payload(fields=DM_WEBHOOK_FIELDS | {"mentions"})
    validate_page_subscription_baseline(payload, expected_app_id="999000111222333")
    with pytest.raises(MetaTokenValidationError) as exc:
        validate_page_subscription_configuration(
            payload,
            expected_app_id="999000111222333",
            expect_facebook_comment_delivery=False,
        )
    assert "subscribed_fields_extra=['mentions']" in str(exc.value)


def test_page_subscription_feed_present_does_not_fail_baseline() -> None:
    checks = validate_page_subscription_baseline(
        _page_subscription_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        expected_app_id="999000111222333",
    )
    assert checks["page_subscribed_dm_fields_present"] is True


def test_production_app_webhook_configuration_passes() -> None:
    checks = validate_app_webhook_configuration(_app_webhook_payload())

    assert checks["app_page_webhook_fields_exact"] is True
    assert checks["app_instagram_webhook_fields_exact"] is True
    assert checks["app_page_webhook_dm_fields_present"] is True
    assert checks["app_instagram_webhook_dm_fields_present"] is True
    assert checks["app_page_webhook_callback_match"] is True
    assert checks["app_instagram_webhook_callback_match"] is True


def test_app_webhook_validation_allows_separate_whatsapp_subscription() -> None:
    payload = _app_webhook_payload()
    data = payload["data"]
    assert isinstance(data, list)
    data.append(
        {
            "object": "whatsapp_business_account",
            "callback_url": "https://www.linasaibot.com/webhook/whatsapp-cloud",
            "active": True,
            "fields": [{"name": "messages"}],
        }
    )

    checks = validate_app_webhook_configuration(payload)

    assert checks["app_social_webhook_objects_exact"] is True
    assert checks["app_auxiliary_webhook_objects_supported"] is True


def test_legacy_dm_only_app_webhook_configuration_fails() -> None:
    with pytest.raises(MetaTokenValidationError) as exc:
        validate_app_webhook_configuration(
            _app_webhook_payload(
                page_fields=sorted(DM_WEBHOOK_FIELDS),
                instagram_fields=sorted(DM_WEBHOOK_FIELDS),
            )
        )
    message = str(exc.value)
    assert "page_fields_missing=['feed']" in message
    assert "instagram_fields_missing=['comments']" in message


@pytest.mark.parametrize(
    "failure",
    ["missing_instagram", "inactive_page", "wrong_callback", "extra_object", "extra_field", "missing_dm_field"],
)
def test_app_webhook_mismatch_fails_closed(failure: str) -> None:
    page_fields = sorted(APP_PAGE_WEBHOOK_FIELDS)
    instagram_fields = sorted(APP_INSTAGRAM_WEBHOOK_FIELDS)
    page: dict[str, object] = {
        "object": "page",
        "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
        "active": True,
        "fields": [{"name": field} for field in page_fields],
    }
    instagram: dict[str, object] = {
        "object": "instagram",
        "callback_url": "https://www.linasaibot.com/webhook/instagram-login",
        "active": True,
        "fields": [{"name": field} for field in instagram_fields],
    }
    data = [page, instagram]
    if failure == "missing_instagram":
        data = [page]
    elif failure == "inactive_page":
        page["active"] = False
    elif failure == "wrong_callback":
        instagram["callback_url"] = "https://www.linasaibot.com/webhook/meta-messaging"
    elif failure == "extra_object":
        data.append({"object": "user", "active": True, "fields": []})
    elif failure == "extra_field":
        instagram["fields"] = [{"name": field} for field in [*instagram_fields, "mentions"]]
    else:
        page["fields"] = [{"name": "feed"}, {"name": "messages"}]

    with pytest.raises(MetaTokenValidationError):
        validate_app_webhook_configuration({"data": data})


def test_feature_readiness_false_when_comment_and_publish_scopes_missing() -> None:
    readiness = evaluate_feature_readiness(
        scopes={
            "pages_messaging",
            "pages_manage_metadata",
            "pages_show_list",
            "pages_read_engagement",
            "instagram_basic",
            "instagram_manage_messages",
        },
        app_page_fields=set(APP_PAGE_WEBHOOK_FIELDS),
        app_instagram_fields=set(APP_INSTAGRAM_WEBHOOK_FIELDS),
        page_subscribed_fields=set(PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        facebook_comment_switch_enabled=True,
        instagram_comment_switch_enabled=True,
    )
    assert readiness["facebook_comments_ready"] is False
    assert readiness["instagram_comments_ready"] is False
    assert readiness["publish_features_ready"] is False
    for scope in COMMENT_FEATURE_SCOPES | PUBLISH_FEATURE_SCOPES:
        assert readiness[f"scope_{scope}_present"] is False


def test_feature_readiness_true_when_all_layers_present() -> None:
    scopes = {
        "pages_messaging",
        "pages_manage_metadata",
        "pages_show_list",
        "pages_read_engagement",
        "instagram_basic",
        "instagram_manage_messages",
        *COMMENT_FEATURE_SCOPES,
        *PUBLISH_FEATURE_SCOPES,
    }
    readiness = evaluate_feature_readiness(
        scopes=scopes,
        app_page_fields=set(APP_PAGE_WEBHOOK_FIELDS),
        app_instagram_fields=set(APP_INSTAGRAM_WEBHOOK_FIELDS),
        page_subscribed_fields=set(PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        facebook_comment_switch_enabled=True,
        instagram_comment_switch_enabled=True,
    )
    assert readiness["facebook_comments_ready"] is True
    assert readiness["instagram_comments_ready"] is True
    assert readiness["publish_features_ready"] is True


def test_random_superset_app_webhook_fields_fail() -> None:
    with pytest.raises(MetaTokenValidationError) as exc:
        validate_app_webhook_configuration(
            _app_webhook_payload(
                page_fields=sorted(APP_PAGE_WEBHOOK_FIELDS | {"mentions"}),
                instagram_fields=sorted(APP_INSTAGRAM_WEBHOOK_FIELDS),
            )
        )
    assert "page_fields_extra=['mentions']" in str(exc.value)
