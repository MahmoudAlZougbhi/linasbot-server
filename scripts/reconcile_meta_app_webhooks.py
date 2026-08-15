#!/usr/bin/env python3
"""Reconcile App A's Page webhook while preserving Direct Instagram configuration."""

from __future__ import annotations

import importlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import cast

_webhook_contract = importlib.import_module("scripts.meta_webhook_contract" if __package__ else "meta_webhook_contract")

APP_INSTAGRAM_WEBHOOK_FIELDS = _webhook_contract.APP_INSTAGRAM_WEBHOOK_FIELDS
APP_PAGE_WEBHOOK_FIELDS = _webhook_contract.APP_PAGE_WEBHOOK_FIELDS
merge_subscription_fields = _webhook_contract.merge_subscription_fields

EXPECTED_APP_ID = "2963733803971681"
EXPECTED_GRAPH_VERSION = "v24.0"
PAGE_OBJECT = "page"
INSTAGRAM_OBJECT = "instagram"
EXPECTED_PAGE_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"
EXPECTED_INSTAGRAM_CALLBACK_URL = "https://www.linasaibot.com/webhook/instagram-login"
EXPECTED_CALLBACK_URL = EXPECTED_PAGE_CALLBACK_URL
EXPECTED_OBJECTS = (INSTAGRAM_OBJECT, PAGE_OBJECT)
MUTABLE_OBJECTS = (PAGE_OBJECT,)
PRESERVED_AUXILIARY_OBJECTS = frozenset({"whatsapp_business_account"})
ALLOWED_FIELDS_BY_OBJECT = {
    INSTAGRAM_OBJECT: APP_INSTAGRAM_WEBHOOK_FIELDS,
    PAGE_OBJECT: APP_PAGE_WEBHOOK_FIELDS,
}
EXPECTED_CALLBACKS_BY_OBJECT = {
    INSTAGRAM_OBJECT: EXPECTED_INSTAGRAM_CALLBACK_URL,
    PAGE_OBJECT: EXPECTED_PAGE_CALLBACK_URL,
}


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


def _classify_error_message(message: object) -> tuple[str, tuple[str, ...]]:
    """Convert a Meta error message to fixed non-sensitive diagnostic labels."""

    lowered = str(message or "").lower()
    reason = "unknown"
    if "unsupported post request" in lowered or "unsupported get request" in lowered:
        reason = "unsupported_request"
    elif "does not exist" in lowered or "not a valid field" in lowered:
        reason = "unsupported_field"
    elif "invalid parameter" in lowered:
        reason = "invalid_parameter"
    elif "verify_token" in lowered and any(
        term in lowered for term in ("too long", "length", "characters", "maximum", "between")
    ):
        reason = "verify_token_format"
    elif "verify_token" in lowered and ("invalid" in lowered or "not valid" in lowered):
        reason = "verify_token_invalid"
    elif "verify_token" in lowered and ("required" in lowered or "missing" in lowered):
        reason = "verify_token_missing"
    elif "callback" in lowered and ("validat" in lowered or "verify" in lowered):
        reason = "callback_verification"
    elif "permission" in lowered or "access token" in lowered:
        reason = "permission_or_token"

    approved_terms = (
        "callback_url",
        "fields",
        "instagram",
        "messages",
        "messaging_postbacks",
        "object",
        "page",
        "verify_token",
    )
    mentions = tuple(term for term in approved_terms if term in lowered)
    return reason, mentions


def validate_webhook_state(
    payload: dict[str, object],
    *,
    require_expected_fields: bool,
) -> dict[str, set[str]]:
    """Require approved callbacks/fields and optionally the full social contract."""

    raw_subscriptions = payload.get("data")
    subscriptions = raw_subscriptions if isinstance(raw_subscriptions, list) else []
    rows = [subscription for subscription in subscriptions if isinstance(subscription, dict)]
    if len(rows) != len(subscriptions):
        raise MetaWebhookReconcileError("Invalid Meta webhook subscription row")
    names = [str(subscription.get("object") or "").strip().lower() for subscription in rows]
    allowed_objects = set(EXPECTED_OBJECTS) | set(PRESERVED_AUXILIARY_OBJECTS)
    if not set(names).issubset(allowed_objects):
        raise MetaWebhookReconcileError("Unexpected Meta webhook object set")
    by_object: dict[str, dict[str, object]] = {}
    for object_name in EXPECTED_OBJECTS:
        matching = [row for row, name in zip(rows, names, strict=True) if name == object_name]
        if len(matching) != 1:
            raise MetaWebhookReconcileError(f"Expected exactly one Meta webhook object={object_name}")
        by_object[object_name] = matching[0]

    fields_by_object: dict[str, set[str]] = {}
    for object_name in EXPECTED_OBJECTS:
        subscription = _mapping(by_object.get(object_name))
        if subscription.get("active") is not True:
            raise MetaWebhookReconcileError(f"Inactive Meta webhook object={object_name}")
        if str(subscription.get("callback_url") or "") != EXPECTED_CALLBACKS_BY_OBJECT[object_name]:
            raise MetaWebhookReconcileError(f"Unexpected Meta callback object={object_name}")
        fields = _field_names(subscription.get("fields"))
        allowed_fields = ALLOWED_FIELDS_BY_OBJECT[object_name]
        if not fields.issubset(allowed_fields):
            raise MetaWebhookReconcileError(f"Unexpected Meta webhook field object={object_name}")
        if (require_expected_fields or object_name == INSTAGRAM_OBJECT) and fields != allowed_fields:
            raise MetaWebhookReconcileError(f"Incomplete Meta webhook fields object={object_name}")
        fields_by_object[object_name] = fields
    return fields_by_object


def inspect_repairable_webhook_state(payload: dict[str, object]) -> dict[str, set[str]]:
    """Read a safe pre-reconcile state without requiring it to be healthy yet.

    A missing, inactive, or wrong-callback Page row is repairable. The Direct
    Instagram product row is read-only here and must already be uniquely active
    on its dedicated callback with the exact approved fields. Unknown objects,
    duplicate rows, and unapproved fields fail closed.
    """

    raw_subscriptions = payload.get("data")
    subscriptions = raw_subscriptions if isinstance(raw_subscriptions, list) else []
    rows = [subscription for subscription in subscriptions if isinstance(subscription, dict)]
    if len(rows) != len(subscriptions):
        raise MetaWebhookReconcileError("Invalid Meta webhook subscription row")
    names = [str(subscription.get("object") or "").strip().lower() for subscription in rows]
    allowed_objects = set(EXPECTED_OBJECTS) | set(PRESERVED_AUXILIARY_OBJECTS)
    if not set(names).issubset(allowed_objects):
        raise MetaWebhookReconcileError("Unexpected Meta webhook object set")
    if any(names.count(object_name) > 1 for object_name in allowed_objects):
        raise MetaWebhookReconcileError("Duplicate Meta webhook object")

    fields_by_object: dict[str, set[str]] = {}
    for object_name in EXPECTED_OBJECTS:
        matching = [row for row, name in zip(rows, names, strict=True) if name == object_name]
        if object_name == INSTAGRAM_OBJECT:
            if len(matching) != 1:
                raise MetaWebhookReconcileError("Expected exactly one Meta webhook object=instagram")
            instagram = _mapping(matching[0])
            if instagram.get("active") is not True:
                raise MetaWebhookReconcileError("Inactive Meta webhook object=instagram")
            if str(instagram.get("callback_url") or "") != EXPECTED_INSTAGRAM_CALLBACK_URL:
                raise MetaWebhookReconcileError("Unexpected Meta callback object=instagram")
        fields = _field_names(matching[0].get("fields")) if matching else set()
        if not fields.issubset(ALLOWED_FIELDS_BY_OBJECT[object_name]):
            raise MetaWebhookReconcileError(f"Unexpected Meta webhook field object={object_name}")
        if object_name == INSTAGRAM_OBJECT and fields != APP_INSTAGRAM_WEBHOOK_FIELDS:
            raise MetaWebhookReconcileError("Incomplete Meta webhook fields object=instagram")
        fields_by_object[object_name] = fields
    return fields_by_object


def plan_webhook_reconcile(fields_by_object: dict[str, set[str]]) -> dict[str, set[str]]:
    """Converge Page fields while preserving the validated Instagram row."""

    targets: dict[str, set[str]] = {}
    for object_name in EXPECTED_OBJECTS:
        current = set(fields_by_object.get(object_name, set()))
        if not current.issubset(ALLOWED_FIELDS_BY_OBJECT[object_name]):
            raise MetaWebhookReconcileError(f"Unexpected Meta webhook field object={object_name}")
        targets[object_name] = (
            set(current)
            if object_name == INSTAGRAM_OBJECT
            else merge_subscription_fields(current, ALLOWED_FIELDS_BY_OBJECT[object_name])
        )
    return targets


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
        error_type = "unknown"
        error_code = 0
        error_subcode = 0
        error_reason = "unknown"
        error_mentions: tuple[str, ...] = ()
        try:
            error_payload: object = json.loads(exc.read(1_000_000))
        except (AttributeError, json.JSONDecodeError):
            error_payload = {}
        error = _mapping(_mapping(error_payload).get("error"))
        error_reason, error_mentions = _classify_error_message(error.get("message"))
        raw_type = str(error.get("type") or "unknown")
        if raw_type.replace("_", "").isalnum():
            error_type = raw_type[:64]
        if isinstance(error.get("code"), int):
            error_code = cast(int, error["code"])
        if isinstance(error.get("error_subcode"), int):
            error_subcode = cast(int, error["error_subcode"])
        raise MetaWebhookReconcileError(
            f"Meta webhook request failed stage={stage} http={exc.code} "
            f"type={error_type} code={error_code} subcode={error_subcode} "
            f"reason={error_reason} mentions={','.join(error_mentions) or 'none'}"
        ) from None
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
    print(f"[meta-webhooks] verify_token_length={len(verify_token)}")

    app_token = f"{app_id}|{app_secret}"
    base_url = f"https://graph.facebook.com/{version}/{app_id}/subscriptions"
    fields_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    before = _request_json(
        f"{base_url}?{fields_query}",
        bearer=app_token,
        stage="read_before",
    )
    before_fields = inspect_repairable_webhook_state(before)
    target_fields = plan_webhook_reconcile(before_fields)
    for object_name in EXPECTED_OBJECTS:
        print(f"[meta-webhooks] before_{object_name}_fields={','.join(sorted(before_fields[object_name])) or 'none'}")

    for object_name in MUTABLE_OBJECTS:
        result = _request_json(
            base_url,
            bearer=app_token,
            method="POST",
            form={
                "object": object_name,
                "callback_url": EXPECTED_CALLBACKS_BY_OBJECT[object_name],
                "verify_token": verify_token,
                "fields": ",".join(sorted(target_fields[object_name])),
            },
            stage=f"reconcile_{object_name}",
        )
        if result.get("success") is not True:
            raise MetaWebhookReconcileError(f"Meta did not confirm object={object_name}")
        print(f"[meta-webhooks] reconciled_{object_name}=true")
    print("[meta-webhooks] instagram_preserved_read_only=true")

    after = _request_json(
        f"{base_url}?{fields_query}",
        bearer=app_token,
        stage="read_after",
    )
    after_fields = validate_webhook_state(after, require_expected_fields=True)
    for object_name in EXPECTED_OBJECTS:
        if after_fields[object_name] != target_fields[object_name]:
            raise MetaWebhookReconcileError(f"Unexpected reconciled fields object={object_name}")
        print(f"[meta-webhooks] after_{object_name}_fields={','.join(sorted(after_fields[object_name]))}")
    print("[meta-webhooks] callback_match=true")
    print("[meta-webhooks] SUCCESS")


if __name__ == "__main__":
    main()
