#!/usr/bin/env python3
"""Idempotently add Meta comment webhook fields without removing DM subscriptions."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import cast

from services.meta_comment_webhooks import (
    INSTAGRAM_APP_COMMENT_FIELDS,
    PAGE_COMMENT_FIELDS,
)

EXPECTED_APP_ID = "2963733803971681"
EXPECTED_GRAPH_VERSION = "v24.0"
EXPECTED_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"
PAGE_OBJECT = "page"
INSTAGRAM_OBJECT = "instagram"
PAGE_FIELDS = set(PAGE_COMMENT_FIELDS)
INSTAGRAM_FIELDS = set(INSTAGRAM_APP_COMMENT_FIELDS)
DM_FIELDS = {"messages", "messaging_postbacks"}


class MetaCommentWebhookReconcileError(RuntimeError):
    pass


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _field_names(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    names: set[str] = set()
    for item in value:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item).strip()
        if name:
            names.add(name)
    return names


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


def _merge_fields(current: set[str], required: set[str]) -> set[str]:
    merged = set(current) | set(required)
    if not DM_FIELDS.issubset(merged):
        raise MetaCommentWebhookReconcileError("DM webhook fields would be removed")
    return merged


def main() -> None:
    app_id = (os.environ.get("META_APP_ID") or "").strip()
    app_secret = (os.environ.get("META_APP_SECRET") or "").strip()
    verify_token = (os.environ.get("META_WEBHOOK_VERIFY_TOKEN") or "").strip()
    version = (os.environ.get("META_GRAPH_API_VERSION") or "").strip()
    if app_id != EXPECTED_APP_ID:
        raise MetaCommentWebhookReconcileError("Refusing an unexpected Meta App ID")
    if version != EXPECTED_GRAPH_VERSION:
        raise MetaCommentWebhookReconcileError("Refusing an unexpected Graph API version")
    if not app_secret or len(verify_token) < 32:
        raise MetaCommentWebhookReconcileError("Required Meta credentials are missing or malformed")

    app_token = f"{app_id}|{app_secret}"
    base_url = f"https://graph.facebook.com/{version}/{app_id}/subscriptions"
    fields_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    before = _request_json(f"{base_url}?{fields_query}", bearer=app_token, stage="read_before")
    subscriptions_raw = before.get("data")
    subscriptions: list[dict[str, object]] = (
        cast(list[dict[str, object]], subscriptions_raw) if isinstance(subscriptions_raw, list) else []
    )
    by_object = {str(row.get("object") or "").strip().lower(): row for row in subscriptions if isinstance(row, dict)}
    page_before = _field_names(_mapping(by_object.get(PAGE_OBJECT)).get("fields"))
    ig_before = _field_names(_mapping(by_object.get(INSTAGRAM_OBJECT)).get("fields"))
    page_target = _merge_fields(page_before, PAGE_FIELDS)
    ig_target = _merge_fields(ig_before, INSTAGRAM_FIELDS)
    print(f"[meta-comment-webhooks] before_page_fields={','.join(sorted(page_before)) or 'none'}")
    print(f"[meta-comment-webhooks] before_instagram_fields={','.join(sorted(ig_before)) or 'none'}")

    for object_name, target_fields in ((PAGE_OBJECT, page_target), (INSTAGRAM_OBJECT, ig_target)):
        result = _request_json(
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
        if result.get("success") is not True:
            raise MetaCommentWebhookReconcileError(f"Meta did not confirm object={object_name}")
        print(f"[meta-comment-webhooks] reconciled_{object_name}=true fields={','.join(sorted(target_fields))}")

    after = _request_json(f"{base_url}?{fields_query}", bearer=app_token, stage="read_after")
    subscriptions_after_raw = after.get("data")
    subscriptions_after: list[dict[str, object]] = (
        cast(list[dict[str, object]], subscriptions_after_raw) if isinstance(subscriptions_after_raw, list) else []
    )
    by_object_after = {
        str(row.get("object") or "").strip().lower(): row for row in subscriptions_after if isinstance(row, dict)
    }
    page_after = _field_names(_mapping(by_object_after.get(PAGE_OBJECT)).get("fields"))
    ig_after = _field_names(_mapping(by_object_after.get(INSTAGRAM_OBJECT)).get("fields"))
    if not PAGE_FIELDS.issubset(page_after):
        raise MetaCommentWebhookReconcileError("Page comment fields missing after reconcile")
    if not INSTAGRAM_FIELDS.issubset(ig_after):
        raise MetaCommentWebhookReconcileError("Instagram comment fields missing after reconcile")
    if not DM_FIELDS.issubset(page_after) or not DM_FIELDS.issubset(ig_after):
        raise MetaCommentWebhookReconcileError("DM fields missing after reconcile")
    print("[meta-comment-webhooks] SUCCESS")


if __name__ == "__main__":
    main()
