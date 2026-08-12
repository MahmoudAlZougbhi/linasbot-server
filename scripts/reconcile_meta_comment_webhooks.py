#!/usr/bin/env python3
"""Idempotently add Meta comment webhook fields without removing DM subscriptions."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol, cast

from scripts.meta_webhook_contract import (
    APP_INSTAGRAM_WEBHOOK_FIELDS,
    APP_PAGE_WEBHOOK_FIELDS,
    DM_WEBHOOK_FIELDS,
    plan_page_subscription_reconcile,
    subscription_field_names,
)

EXPECTED_APP_ID = "2963733803971681"
EXPECTED_PAGE_ID = "378696005334409"
EXPECTED_GRAPH_VERSION = "v24.0"
EXPECTED_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"
PAGE_OBJECT = "page"
INSTAGRAM_OBJECT = "instagram"


class MetaCommentWebhookReconcileError(RuntimeError):
    pass


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _request_json(
    url: str,
    *,
    bearer: str,
    method: str = "GET",
    form: dict[str, str] | None = None,
    stage: str,
) -> dict[str, object]:
    body = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    headers = {"Accept": "application/json", "Authorization": f"Bearer {bearer}"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            decoded: object = json.loads(response.read(1_000_000))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise MetaCommentWebhookReconcileError(f"Meta webhook request failed stage={stage}") from exc
    if not isinstance(decoded, dict):
        raise MetaCommentWebhookReconcileError(f"Meta webhook response invalid stage={stage}")
    return cast(dict[str, object], decoded)


def merge_app_subscription_fields(current: set[str], required: frozenset[str]) -> Any:
    merged = set(current) | set(required)
    if not DM_WEBHOOK_FIELDS.issubset(merged):
        raise MetaCommentWebhookReconcileError("DM webhook fields would be removed")
    return merged


def plan_app_subscription_reconcile(
    *,
    page_fields: set[str],
    instagram_fields: set[str],
) -> tuple[set[str], set[str]]:
    return (
        merge_app_subscription_fields(page_fields, APP_PAGE_WEBHOOK_FIELDS),
        merge_app_subscription_fields(instagram_fields, APP_INSTAGRAM_WEBHOOK_FIELDS),
    )


class GraphRequest(Protocol):
    def __call__(
        self,
        url: str,
        *,
        bearer: str,
        method: str = "GET",
        form: dict[str, str] | None = None,
        stage: str,
    ) -> dict[str, object]: ...


def reconcile_app_subscriptions(
    *,
    app_id: str,
    app_secret: str,
    verify_token: str,
    version: str,
    request_json: GraphRequest = _request_json,
) -> tuple[set[str], set[str]]:
    """Merge app-level webhook fields for Page and Instagram objects."""

    app_token = f"{app_id}|{app_secret}"
    base_url = f"https://graph.facebook.com/{version}/{app_id}/subscriptions"
    fields_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    request = request_json
    before = request(f"{base_url}?{fields_query}", bearer=app_token, stage="read_before")
    subscriptions_raw = before.get("data") if isinstance(before, dict) else None
    subscriptions: list[dict[str, object]] = (
        cast(list[dict[str, object]], subscriptions_raw) if isinstance(subscriptions_raw, list) else []
    )
    by_object = {str(row.get("object") or "").strip().lower(): row for row in subscriptions if isinstance(row, dict)}
    page_before = subscription_field_names(_mapping(by_object.get(PAGE_OBJECT)).get("fields"))
    ig_before = subscription_field_names(_mapping(by_object.get(INSTAGRAM_OBJECT)).get("fields"))
    page_target, ig_target = plan_app_subscription_reconcile(page_fields=page_before, instagram_fields=ig_before)

    for object_name, target_fields in ((PAGE_OBJECT, page_target), (INSTAGRAM_OBJECT, ig_target)):
        result = request(
            base_url,
            bearer=app_token,
            method="POST",
            form={
                "object": object_name,
                "callback_url": EXPECTED_CALLBACK_URL,
                "verify_token": verify_token,
                "fields": ",".join(sorted(target_fields)),
            },
            stage=f"reconcile_{object_name}",
        )
        if not isinstance(result, dict) or result.get("success") is not True:
            raise MetaCommentWebhookReconcileError(f"Meta did not confirm object={object_name}")

    after = request(f"{base_url}?{fields_query}", bearer=app_token, stage="read_after")
    subscriptions_after_raw = after.get("data") if isinstance(after, dict) else None
    subscriptions_after: list[dict[str, object]] = (
        cast(list[dict[str, object]], subscriptions_after_raw) if isinstance(subscriptions_after_raw, list) else []
    )
    by_object_after = {
        str(row.get("object") or "").strip().lower(): row for row in subscriptions_after if isinstance(row, dict)
    }
    page_after = subscription_field_names(_mapping(by_object_after.get(PAGE_OBJECT)).get("fields"))
    ig_after = subscription_field_names(_mapping(by_object_after.get(INSTAGRAM_OBJECT)).get("fields"))
    if not APP_PAGE_WEBHOOK_FIELDS.issubset(page_after):
        raise MetaCommentWebhookReconcileError("Page comment fields missing after reconcile")
    if not APP_INSTAGRAM_WEBHOOK_FIELDS.issubset(ig_after):
        raise MetaCommentWebhookReconcileError("Instagram comment fields missing after reconcile")
    if not DM_WEBHOOK_FIELDS.issubset(page_after) or not DM_WEBHOOK_FIELDS.issubset(ig_after):
        raise MetaCommentWebhookReconcileError("DM fields missing after reconcile")
    return page_after, ig_after


def reconcile_page_subscription(
    *,
    page_id: str,
    page_token: str,
    version: str,
    current_fields: set[str],
    request_json: GraphRequest = _request_json,
) -> Any:
    """Idempotently add Page-level feed while preserving DM subscribed fields."""

    target_fields = plan_page_subscription_reconcile(current_fields)
    result = request_json(
        f"https://graph.facebook.com/{version}/{page_id}/subscribed_apps",
        bearer=page_token,
        method="POST",
        form={"subscribed_fields": ",".join(sorted(target_fields))},
        stage="reconcile_page_subscription",
    )
    if not isinstance(result, dict) or result.get("success") is not True:
        raise MetaCommentWebhookReconcileError("Meta did not confirm page subscribed_apps reconcile")
    if not DM_WEBHOOK_FIELDS.issubset(target_fields):
        raise MetaCommentWebhookReconcileError("DM fields missing after page reconcile plan")
    return target_fields


def main() -> None:
    app_id = (os.environ.get("META_APP_ID") or "").strip()
    app_secret = (os.environ.get("META_APP_SECRET") or "").strip()
    verify_token = (os.environ.get("META_WEBHOOK_VERIFY_TOKEN") or "").strip()
    version = (os.environ.get("META_GRAPH_API_VERSION") or "").strip()
    page_token = (os.environ.get("META_PAGE_ACCESS_TOKEN") or "").strip()
    page_id = (os.environ.get("META_PAGE_ID") or EXPECTED_PAGE_ID).strip()
    reconcile_page = os.environ.get("META_RECONCILE_PAGE_SUBSCRIPTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if app_id != EXPECTED_APP_ID:
        raise MetaCommentWebhookReconcileError("Refusing an unexpected Meta App ID")
    if version != EXPECTED_GRAPH_VERSION:
        raise MetaCommentWebhookReconcileError("Refusing an unexpected Graph API version")
    if not app_secret or len(verify_token) < 32:
        raise MetaCommentWebhookReconcileError("Required Meta credentials are missing or malformed")
    if reconcile_page and not page_token:
        raise MetaCommentWebhookReconcileError("Page subscription reconcile requested without page token")

    page_after, ig_after = reconcile_app_subscriptions(
        app_id=app_id,
        app_secret=app_secret,
        verify_token=verify_token,
        version=version,
    )
    print(f"[meta-comment-webhooks] app_page_fields={','.join(sorted(page_after))}")
    print(f"[meta-comment-webhooks] app_instagram_fields={','.join(sorted(ig_after))}")

    if reconcile_page:
        fields_query = urllib.parse.urlencode({"fields": "id,subscribed_fields"})
        before_page = _request_json(
            f"https://graph.facebook.com/{version}/{page_id}/subscribed_apps?{fields_query}",
            bearer=page_token,
            stage="read_page_before",
        )
        raw_apps = before_page.get("data")
        apps = raw_apps if isinstance(raw_apps, list) else []
        current_fields = (
            subscription_field_names(_mapping(apps[0]).get("subscribed_fields")) if len(apps) == 1 else set()
        )
        print(f"[meta-comment-webhooks] before_page_subscription_fields={','.join(sorted(current_fields)) or 'none'}")
        target_fields = reconcile_page_subscription(
            page_id=page_id,
            page_token=page_token,
            version=version,
            current_fields=current_fields,
        )
        print(f"[meta-comment-webhooks] reconciled_page_subscription=true fields={','.join(sorted(target_fields))}")

    print("[meta-comment-webhooks] SUCCESS")


if __name__ == "__main__":
    main()
