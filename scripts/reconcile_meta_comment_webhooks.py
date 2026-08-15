#!/usr/bin/env python3
"""Idempotently add Meta comment webhook fields without removing DM subscriptions."""

from __future__ import annotations

import importlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol, cast

_webhook_contract = importlib.import_module("scripts.meta_webhook_contract" if __package__ else "meta_webhook_contract")
_app_webhooks = importlib.import_module(
    "scripts.reconcile_meta_app_webhooks" if __package__ else "reconcile_meta_app_webhooks"
)

APP_INSTAGRAM_WEBHOOK_FIELDS = _webhook_contract.APP_INSTAGRAM_WEBHOOK_FIELDS
APP_PAGE_WEBHOOK_FIELDS = _webhook_contract.APP_PAGE_WEBHOOK_FIELDS
DM_WEBHOOK_FIELDS = _webhook_contract.DM_WEBHOOK_FIELDS
plan_page_subscription_reconcile = _webhook_contract.plan_page_subscription_reconcile
subscription_field_names = _webhook_contract.subscription_field_names
EXPECTED_PAGE_CALLBACK_URL = _app_webhooks.EXPECTED_PAGE_CALLBACK_URL
INSTAGRAM_OBJECT = _app_webhooks.INSTAGRAM_OBJECT
PAGE_OBJECT = _app_webhooks.PAGE_OBJECT
MetaWebhookReconcileError = _app_webhooks.MetaWebhookReconcileError
inspect_repairable_webhook_state = _app_webhooks.inspect_repairable_webhook_state
validate_webhook_state = _app_webhooks.validate_webhook_state

EXPECTED_APP_ID = "2963733803971681"
EXPECTED_PAGE_ID = "378696005334409"
EXPECTED_GRAPH_VERSION = "v24.0"
EXPECTED_CALLBACK_URL = EXPECTED_PAGE_CALLBACK_URL


class MetaCommentWebhookReconcileError(RuntimeError):
    pass


def _page_subscription_writer_lock(*, page_id: str) -> AbstractContextManager[None]:
    """Use the same Page-wide lock as OAuth/API writers on every HA node."""

    import sys

    repo_dir = str(Path(__file__).resolve().parents[1])
    if repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)
    from services.meta_oauth_page_lock import (
        lock_facebook_page_subscription_operation_sync,
        page_lock_target_from_env_file,
    )

    return lock_facebook_page_subscription_operation_sync(
        app_key="app_a",
        page_ids=(page_id,),
        target=page_lock_target_from_env_file(Path(os.environ.get("META_ENV_PATH", "/opt/linasbot/.env"))),
    )


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
    if instagram_fields != APP_INSTAGRAM_WEBHOOK_FIELDS:
        raise MetaCommentWebhookReconcileError(
            "Direct Instagram webhook fields must already match the dedicated product contract"
        )
    return (
        merge_app_subscription_fields(page_fields, APP_PAGE_WEBHOOK_FIELDS),
        set(instagram_fields),
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
    """Repair only Page app fields; validate Direct Instagram read-only."""

    app_token = f"{app_id}|{app_secret}"
    base_url = f"https://graph.facebook.com/{version}/{app_id}/subscriptions"
    fields_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    request = request_json
    before = request(f"{base_url}?{fields_query}", bearer=app_token, stage="read_before")
    try:
        before_fields = inspect_repairable_webhook_state(before)
    except MetaWebhookReconcileError as exc:
        raise MetaCommentWebhookReconcileError(str(exc)) from exc
    page_before = before_fields[PAGE_OBJECT]
    ig_before = before_fields[INSTAGRAM_OBJECT]
    page_target, ig_target = plan_app_subscription_reconcile(page_fields=page_before, instagram_fields=ig_before)

    result = request(
        base_url,
        bearer=app_token,
        method="POST",
        form={
            "object": PAGE_OBJECT,
            "callback_url": EXPECTED_PAGE_CALLBACK_URL,
            "verify_token": verify_token,
            "fields": ",".join(sorted(page_target)),
        },
        stage="reconcile_page",
    )
    if not isinstance(result, dict) or result.get("success") is not True:
        raise MetaCommentWebhookReconcileError("Meta did not confirm object=page")

    after = request(f"{base_url}?{fields_query}", bearer=app_token, stage="read_after")
    try:
        after_fields = validate_webhook_state(after, require_expected_fields=True)
    except MetaWebhookReconcileError as exc:
        raise MetaCommentWebhookReconcileError(str(exc)) from exc
    page_after = after_fields[PAGE_OBJECT]
    ig_after = after_fields[INSTAGRAM_OBJECT]
    if page_after != page_target or ig_after != ig_target:
        raise MetaCommentWebhookReconcileError("Meta app webhook fields did not converge exactly")
    return page_after, ig_after


def _page_fields_for_app(
    payload: dict[str, object],
    *,
    app_id: str,
    allow_absent: bool,
) -> set[str]:
    rows_raw = payload.get("data")
    rows = rows_raw if isinstance(rows_raw, list) else []
    if any(not isinstance(row, dict) for row in rows):
        raise MetaCommentWebhookReconcileError("Invalid Page subscribed_apps row")
    app_ids = {str(row.get("id") or "") for row in rows if isinstance(row, dict)}
    if app_ids - {app_id}:
        raise MetaCommentWebhookReconcileError("Unexpected app in Page subscribed_apps")
    matching = [row for row in rows if isinstance(row, dict) and str(row.get("id") or "") == app_id]
    if not matching and allow_absent:
        return set()
    if len(matching) != 1:
        raise MetaCommentWebhookReconcileError("Configured app Page subscription is not unique")
    raw_fields = subscription_field_names(matching[0].get("subscribed_fields"))
    if not isinstance(raw_fields, (set, frozenset, list, tuple)):
        raise MetaCommentWebhookReconcileError("Invalid Page subscribed_fields value")
    return {str(field) for field in raw_fields if str(field)}


def reconcile_page_subscription(
    *,
    page_id: str,
    app_id: str,
    page_token: str,
    version: str,
    current_fields: set[str],
    request_json: GraphRequest = _request_json,
) -> Any:
    """Idempotently add Page-level feed while preserving DM subscribed fields."""

    del current_fields
    with _page_subscription_writer_lock(page_id=page_id):
        fields_query = urllib.parse.urlencode({"fields": "id,subscribed_fields"})
        locked_before = request_json(
            f"https://graph.facebook.com/{version}/{page_id}/subscribed_apps?{fields_query}",
            bearer=page_token,
            stage="read_page_under_lock",
        )
        locked_fields = _page_fields_for_app(locked_before, app_id=app_id, allow_absent=True)
        target_fields = plan_page_subscription_reconcile(locked_fields)
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
        verified = request_json(
            f"https://graph.facebook.com/{version}/{page_id}/subscribed_apps?{fields_query}",
            bearer=page_token,
            stage="verify_page_subscription",
        )
        verified_fields = _page_fields_for_app(verified, app_id=app_id, allow_absent=False)
        if verified_fields != target_fields:
            raise MetaCommentWebhookReconcileError("Page subscribed_apps did not converge exactly")
        return verified_fields


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
    if page_id != EXPECTED_PAGE_ID:
        raise MetaCommentWebhookReconcileError("Refusing an unexpected Facebook Page")
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
        current_fields = _page_fields_for_app(before_page, app_id=app_id, allow_absent=True)
        print(f"[meta-comment-webhooks] before_page_subscription_fields={','.join(sorted(current_fields)) or 'none'}")
        target_fields = reconcile_page_subscription(
            page_id=page_id,
            app_id=app_id,
            page_token=page_token,
            version=version,
            current_fields=current_fields,
        )
        print(f"[meta-comment-webhooks] reconciled_page_subscription=true fields={','.join(sorted(target_fields))}")

    print("[meta-comment-webhooks] SUCCESS")


if __name__ == "__main__":
    main()
