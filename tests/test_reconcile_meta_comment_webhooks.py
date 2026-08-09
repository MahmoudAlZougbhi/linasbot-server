"""Unit tests for Meta comment webhook reconcile helpers."""

from __future__ import annotations

from scripts.meta_webhook_contract import DM_WEBHOOK_FIELDS, PAGE_SUBSCRIPTION_COMMENT_DELIVERY
from scripts.reconcile_meta_comment_webhooks import (
    merge_app_subscription_fields,
    plan_app_subscription_reconcile,
    reconcile_page_subscription,
)


def test_merge_app_subscription_fields_preserves_dm_when_adding_feed() -> None:
    merged = merge_app_subscription_fields(set(DM_WEBHOOK_FIELDS), PAGE_SUBSCRIPTION_COMMENT_DELIVERY)

    assert DM_WEBHOOK_FIELDS.issubset(merged)
    assert "feed" in merged


def test_plan_app_subscription_reconcile_targets_comment_fields() -> None:
    page_target, ig_target = plan_app_subscription_reconcile(
        page_fields=set(DM_WEBHOOK_FIELDS),
        instagram_fields=set(DM_WEBHOOK_FIELDS),
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
        del url, bearer, method, stage
        assert form is not None
        calls.append(dict(form))
        return {"success": True}

    first = reconcile_page_subscription(
        page_id="378696005334409",
        page_token="page-token",
        version="v24.0",
        current_fields=set(DM_WEBHOOK_FIELDS),
        request_json=fake_request,
    )
    second = reconcile_page_subscription(
        page_id="378696005334409",
        page_token="page-token",
        version="v24.0",
        current_fields=first,
        request_json=fake_request,
    )

    assert first == second == set(PAGE_SUBSCRIPTION_COMMENT_DELIVERY)
    assert calls[0]["subscribed_fields"] == "feed,messages,messaging_postbacks"
    assert calls[1]["subscribed_fields"] == "feed,messages,messaging_postbacks"
