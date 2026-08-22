"""Unit tests for Meta webhook subscription contracts."""

from __future__ import annotations

import pytest

from scripts.meta_webhook_contract import (
    APP_INSTAGRAM_WEBHOOK_FIELDS,
    APP_PAGE_WEBHOOK_FIELDS,
    DM_WEBHOOK_FIELDS,
    PAGE_SUBSCRIPTION_COMMENT_DELIVERY,
    PAGE_SUBSCRIPTION_DM_ONLY,
    assert_page_subscription_baseline,
    assert_page_subscription_configuration,
    evaluate_feature_readiness,
    plan_page_subscription_reconcile,
)


class ContractError(RuntimeError):
    pass


def _page_payload(*, fields: set[str], app_id: str = "999000111222333") -> dict[str, object]:
    return {
        "data": [
            {
                "id": app_id,
                "subscribed_fields": sorted(fields),
            }
        ]
    }


def test_page_dm_only_baseline_true_comments_delivery_false() -> None:
    checks = assert_page_subscription_baseline(
        _page_payload(fields=DM_WEBHOOK_FIELDS),
        expected_app_id="999000111222333",
        error_type=ContractError,
    )
    config = assert_page_subscription_configuration(
        _page_payload(fields=PAGE_SUBSCRIPTION_DM_ONLY),
        expected_app_id="999000111222333",
        expect_facebook_comment_delivery=False,
        error_type=ContractError,
    )

    assert checks["page_subscribed_dm_fields_present"] is True
    assert config["facebook_comment_delivery_infrastructure_ready"] is False
    assert config["facebook_comment_delivery_profile_matches_expectation"] is True


def test_page_feed_plus_dm_baseline_true_comments_delivery_true() -> None:
    checks = assert_page_subscription_baseline(
        _page_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        expected_app_id="999000111222333",
        error_type=ContractError,
    )
    config = assert_page_subscription_configuration(
        _page_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        expected_app_id="999000111222333",
        expect_facebook_comment_delivery=True,
        error_type=ContractError,
    )

    assert checks["page_subscribed_dm_fields_present"] is True
    assert config["facebook_comment_delivery_infrastructure_ready"] is True
    assert config["facebook_comment_delivery_profile_matches_expectation"] is True


def test_comments_expected_but_feed_missing_configuration_fails() -> None:
    with pytest.raises(ContractError) as exc:
        assert_page_subscription_configuration(
            _page_payload(fields=DM_WEBHOOK_FIELDS),
            expected_app_id="999000111222333",
            expect_facebook_comment_delivery=True,
            error_type=ContractError,
        )
    assert "expect_facebook_comment_delivery=true" in str(exc.value)
    assert "feed" in str(exc.value)


def test_feed_present_comments_disabled_baseline_stays_true() -> None:
    checks = assert_page_subscription_baseline(
        _page_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        expected_app_id="999000111222333",
        error_type=ContractError,
    )
    config = assert_page_subscription_configuration(
        _page_payload(fields=PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        expected_app_id="999000111222333",
        expect_facebook_comment_delivery=False,
        error_type=ContractError,
    )

    assert checks["page_subscribed_dm_fields_present"] is True
    assert config["facebook_comment_delivery_infrastructure_ready"] is True
    assert config["facebook_comment_delivery_profile_matches_expectation"] is True


def test_missing_dm_field_baseline_fails() -> None:
    with pytest.raises(ContractError) as exc:
        assert_page_subscription_baseline(
            _page_payload(fields={"messages"}),
            expected_app_id="999000111222333",
            error_type=ContractError,
        )
    assert "baseline failed" in str(exc.value)
    assert "messaging_postbacks" in str(exc.value)


def test_random_extra_field_configuration_fails_with_clear_message() -> None:
    with pytest.raises(ContractError) as exc:
        assert_page_subscription_configuration(
            _page_payload(fields=DM_WEBHOOK_FIELDS | {"mentions"}),
            expected_app_id="999000111222333",
            expect_facebook_comment_delivery=False,
            error_type=ContractError,
        )
    message = str(exc.value)
    assert "subscribed_fields_extra=['mentions']" in message


def test_feature_readiness_facebook_comments_requires_all_layers() -> None:
    dm_scopes = {
        "pages_messaging",
        "pages_manage_metadata",
        "pages_show_list",
        "pages_read_engagement",
        "instagram_basic",
        "instagram_manage_messages",
    }
    comment_scopes = {"pages_read_user_content", "pages_manage_engagement"}

    readiness = evaluate_feature_readiness(
        scopes=dm_scopes,
        app_page_fields=set(APP_PAGE_WEBHOOK_FIELDS),
        app_instagram_fields=set(APP_INSTAGRAM_WEBHOOK_FIELDS),
        page_subscribed_fields=set(DM_WEBHOOK_FIELDS),
        facebook_comment_switch_enabled=True,
        instagram_comment_switch_enabled=False,
    )
    assert readiness["facebook_comment_delivery_infrastructure_ready"] is False
    assert readiness["facebook_comments_ready"] is False

    readiness = evaluate_feature_readiness(
        scopes=dm_scopes | comment_scopes,
        app_page_fields=set(APP_PAGE_WEBHOOK_FIELDS),
        app_instagram_fields=set(APP_INSTAGRAM_WEBHOOK_FIELDS),
        page_subscribed_fields=set(PAGE_SUBSCRIPTION_COMMENT_DELIVERY),
        facebook_comment_switch_enabled=True,
        instagram_comment_switch_enabled=False,
    )
    assert readiness["facebook_comments_ready"] is True


def test_feature_readiness_instagram_comments_uses_app_instagram_not_page_fields() -> None:
    readiness = evaluate_feature_readiness(
        scopes={
            "pages_messaging",
            "instagram_basic",
            "instagram_manage_messages",
            "instagram_manage_comments",
        },
        app_page_fields=set(APP_PAGE_WEBHOOK_FIELDS),
        app_instagram_fields=set(APP_INSTAGRAM_WEBHOOK_FIELDS),
        page_subscribed_fields=set(DM_WEBHOOK_FIELDS),
        facebook_comment_switch_enabled=False,
        instagram_comment_switch_enabled=True,
    )
    assert readiness["instagram_comments_ready"] is True


def test_feature_readiness_publish_independent_from_comment_webhooks() -> None:
    readiness = evaluate_feature_readiness(
        scopes={"pages_manage_posts", "instagram_content_publish"},
        app_page_fields=set(DM_WEBHOOK_FIELDS),
        app_instagram_fields=set(DM_WEBHOOK_FIELDS),
        page_subscribed_fields=set(DM_WEBHOOK_FIELDS),
        facebook_comment_switch_enabled=False,
        instagram_comment_switch_enabled=False,
    )
    assert readiness["publish_features_ready"] is True
    assert readiness["facebook_comments_ready"] is False
    assert readiness["instagram_comments_ready"] is False


def test_plan_page_subscription_reconcile_idempotent() -> None:
    first = plan_page_subscription_reconcile(set(DM_WEBHOOK_FIELDS))
    second = plan_page_subscription_reconcile(first)

    assert DM_WEBHOOK_FIELDS.issubset(first)
    assert "feed" in first
    assert "standby" in first
    assert first == second
