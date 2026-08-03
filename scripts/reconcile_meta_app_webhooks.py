#!/usr/bin/env python3
"""Reconcile the dedicated Meta app's Page and Instagram DM webhook fields."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import cast

EXPECTED_APP_ID = "2963733803971681"
EXPECTED_GRAPH_VERSION = "v24.0"
EXPECTED_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"
EXPECTED_OBJECTS = ("instagram", "page")
EXPECTED_FIELDS = {"messages", "messaging_postbacks"}


class MetaWebhookReconcileError(RuntimeError):
    """Raised when app webhook state is outside the approved boundary."""


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


def validate_webhook_state(
    payload: dict[str, object],
    *,
    require_exact_fields: bool,
) -> dict[str, set[str]]:
    """Require exactly the two approved callbacks and no unrelated fields."""

    raw_subscriptions = payload.get("data")
    subscriptions = raw_subscriptions if isinstance(raw_subscriptions, list) else []
    by_object = {
        str(subscription.get("object") or "").strip().lower(): subscription
        for subscription in subscriptions
        if isinstance(subscription, dict)
    }
    if set(by_object) != set(EXPECTED_OBJECTS):
        raise MetaWebhookReconcileError("Unexpected Meta webhook object set")

    fields_by_object: dict[str, set[str]] = {}
    for object_name in EXPECTED_OBJECTS:
        subscription = _mapping(by_object.get(object_name))
        if subscription.get("active") is not True:
            raise MetaWebhookReconcileError(f"Inactive Meta webhook object={object_name}")
        if str(subscription.get("callback_url") or "") != EXPECTED_CALLBACK_URL:
            raise MetaWebhookReconcileError(f"Unexpected Meta callback object={object_name}")
        fields = _field_names(subscription.get("fields"))
        if not fields.issubset(EXPECTED_FIELDS):
            raise MetaWebhookReconcileError(f"Unexpected Meta webhook field object={object_name}")
        if require_exact_fields and fields != EXPECTED_FIELDS:
            raise MetaWebhookReconcileError(f"Incomplete Meta webhook fields object={object_name}")
        fields_by_object[object_name] = fields
    return fields_by_object


def _request_json(
    url: str,
    *,
    bearer: str,
    method: str = "GET",
    form: dict[str, str] | None = None,
    stage: str,
) -> dict[str, object]:
    body = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {bearer}",
    }
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            decoded: object = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise MetaWebhookReconcileError(f"Meta webhook request failed stage={stage} http={exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise MetaWebhookReconcileError(f"Meta webhook request failed stage={stage}") from None
    if not isinstance(decoded, dict):
        raise MetaWebhookReconcileError(f"Meta webhook response invalid stage={stage}")
    return cast(dict[str, object], decoded)


def main() -> None:
    app_id = (os.environ.get("META_APP_ID") or "").strip()
    app_secret = (os.environ.get("META_APP_SECRET") or "").strip()
    verify_token = (os.environ.get("META_WEBHOOK_VERIFY_TOKEN") or "").strip()
    version = (os.environ.get("META_GRAPH_API_VERSION") or "").strip()
    if app_id != EXPECTED_APP_ID:
        raise MetaWebhookReconcileError("Refusing an unexpected Meta App ID")
    if version != EXPECTED_GRAPH_VERSION:
        raise MetaWebhookReconcileError("Refusing an unexpected Graph API version")
    if not app_secret or len(verify_token) < 32:
        raise MetaWebhookReconcileError("Required Meta credentials are missing or malformed")

    app_token = f"{app_id}|{app_secret}"
    base_url = f"https://graph.facebook.com/{version}/{app_id}/subscriptions"
    fields_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    before = _request_json(
        f"{base_url}?{fields_query}",
        bearer=app_token,
        stage="read_before",
    )
    before_fields = validate_webhook_state(before, require_exact_fields=False)
    for object_name in EXPECTED_OBJECTS:
        print(f"[meta-webhooks] before_{object_name}_fields={','.join(sorted(before_fields[object_name])) or 'none'}")

    for object_name in EXPECTED_OBJECTS:
        result = _request_json(
            base_url,
            bearer=app_token,
            method="POST",
            form={
                "object": object_name,
                "callback_url": EXPECTED_CALLBACK_URL,
                "verify_token": verify_token,
                "fields": ",".join(sorted(EXPECTED_FIELDS)),
            },
            stage=f"reconcile_{object_name}",
        )
        if result.get("success") is not True:
            raise MetaWebhookReconcileError(f"Meta did not confirm object={object_name}")
        print(f"[meta-webhooks] reconciled_{object_name}=true")

    after = _request_json(
        f"{base_url}?{fields_query}",
        bearer=app_token,
        stage="read_after",
    )
    after_fields = validate_webhook_state(after, require_exact_fields=True)
    for object_name in EXPECTED_OBJECTS:
        print(f"[meta-webhooks] after_{object_name}_fields={','.join(sorted(after_fields[object_name]))}")
    print("[meta-webhooks] callback_match=true")
    print("[meta-webhooks] SUCCESS")


if __name__ == "__main__":
    main()
