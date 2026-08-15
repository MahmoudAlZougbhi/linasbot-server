"""Unit tests for Meta comment webhook reconcile helpers."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts.meta_webhook_contract import DM_WEBHOOK_FIELDS, PAGE_SUBSCRIPTION_COMMENT_DELIVERY
from scripts.reconcile_meta_comment_webhooks import (
    MetaCommentWebhookReconcileError,
    main,
    merge_app_subscription_fields,
    plan_app_subscription_reconcile,
    reconcile_app_subscriptions,
    reconcile_page_subscription,
)


def test_main_rejects_unexpected_page_before_any_graph_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    monkeypatch.setenv("META_WEBHOOK_VERIFY_TOKEN", "v" * 32)
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_PAGE_ID", "999999999")

    with patch("scripts.reconcile_meta_comment_webhooks._request_json") as request:
        with pytest.raises(MetaCommentWebhookReconcileError, match="unexpected Facebook Page"):
            main()

    request.assert_not_called()


def test_merge_app_subscription_fields_preserves_dm_when_adding_feed() -> None:
    merged = merge_app_subscription_fields(set(DM_WEBHOOK_FIELDS), PAGE_SUBSCRIPTION_COMMENT_DELIVERY)

    assert DM_WEBHOOK_FIELDS.issubset(merged)
    assert "feed" in merged


def test_plan_app_subscription_reconcile_targets_comment_fields() -> None:
    page_target, ig_target = plan_app_subscription_reconcile(
        page_fields=set(DM_WEBHOOK_FIELDS),
        instagram_fields={"comments", "messages", "messaging_postbacks"},
    )

    assert "feed" in page_target
    assert "comments" in ig_target
    assert DM_WEBHOOK_FIELDS.issubset(page_target)
    assert DM_WEBHOOK_FIELDS.issubset(ig_target)


def test_reconcile_page_subscription_adds_feed_without_removing_dm_fields() -> None:
    calls: list[dict[str, str]] = []

    def fake_request(
        url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]:
        del url, bearer, stage
        if method == "POST":
            assert form is not None
            calls.append(dict(form))
            return {"success": True}
        assert form is None
        return {
            "data": [
                {
                    "id": "2963733803971681",
                    "subscribed_fields": ["feed", "messages", "messaging_postbacks"],
                }
            ]
        }

    first = reconcile_page_subscription(
        page_id="378696005334409",
        app_id="2963733803971681",
        page_token="page-token",
        version="v24.0",
        current_fields=set(DM_WEBHOOK_FIELDS),
        request_json=fake_request,
    )
    second = reconcile_page_subscription(
        page_id="378696005334409",
        app_id="2963733803971681",
        page_token="page-token",
        version="v24.0",
        current_fields=first,
        request_json=fake_request,
    )

    assert first == second == set(PAGE_SUBSCRIPTION_COMMENT_DELIVERY)
    assert calls[0]["subscribed_fields"] == "feed,messages,messaging_postbacks"
    assert calls[1]["subscribed_fields"] == "feed,messages,messaging_postbacks"


def test_comment_reconciler_repairs_missing_inactive_or_wrong_callback() -> None:
    calls: list[tuple[str, str]] = []

    def fake_request(
        _url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]:
        del bearer
        calls.append((method, stage))
        if stage == "read_before":
            return {
                "data": [
                    {
                        "object": "page",
                        "callback_url": "https://wrong.example/webhook",
                        "active": False,
                        "fields": ["messages", "messaging_postbacks"],
                    },
                    {
                        "object": "instagram",
                        "callback_url": "https://www.linasaibot.com/webhook/instagram-login",
                        "active": True,
                        "fields": ["comments", "messages", "messaging_postbacks"],
                    },
                ]
            }
        if method == "POST":
            assert form is not None
            return {"success": True}
        return {
            "data": [
                {
                    "object": "page",
                    "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                    "active": True,
                    "fields": ["feed", "messages", "messaging_postbacks"],
                },
                {
                    "object": "instagram",
                    "callback_url": "https://www.linasaibot.com/webhook/instagram-login",
                    "active": True,
                    "fields": ["comments", "messages", "messaging_postbacks"],
                },
            ]
        }

    page, instagram = reconcile_app_subscriptions(
        app_id="2963733803971681",
        app_secret="secret",
        verify_token="verify-token",
        version="v24.0",
        request_json=fake_request,
    )

    assert page == {"feed", "messages", "messaging_postbacks"}
    assert instagram == {"comments", "messages", "messaging_postbacks"}
    assert calls == [
        ("GET", "read_before"),
        ("POST", "reconcile_page"),
        ("GET", "read_after"),
    ]


def test_comment_reconciler_rejects_main_instagram_callback_without_post() -> None:
    calls: list[tuple[str, str]] = []

    def fake_request(
        _url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]:
        del bearer, form
        calls.append((method, stage))
        return {
            "data": [
                {
                    "object": "page",
                    "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                    "active": True,
                    "fields": ["feed", "messages", "messaging_postbacks"],
                },
                {
                    "object": "instagram",
                    "callback_url": "https://www.linasaibot.com/webhook/meta-messaging",
                    "active": True,
                    "fields": ["comments", "messages", "messaging_postbacks"],
                },
            ]
        }

    with pytest.raises(MetaCommentWebhookReconcileError, match="callback object=instagram"):
        reconcile_app_subscriptions(
            app_id="2963733803971681",
            app_secret="secret",
            verify_token="verify-token",
            version="v24.0",
            request_json=fake_request,
        )

    assert calls == [("GET", "read_before")]


def test_page_reconciler_rejects_unverified_post_state() -> None:
    def fake_request(
        _url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]:
        del bearer, form, stage
        if method == "POST":
            return {"success": True}
        return {
            "data": [
                {
                    "id": "2963733803971681",
                    "subscribed_fields": ["messages", "messaging_postbacks"],
                }
            ]
        }

    with pytest.raises(MetaCommentWebhookReconcileError, match="did not converge"):
        reconcile_page_subscription(
            page_id="378696005334409",
            app_id="2963733803971681",
            page_token="page-token",
            version="v24.0",
            current_fields=set(DM_WEBHOOK_FIELDS),
            request_json=fake_request,
        )
