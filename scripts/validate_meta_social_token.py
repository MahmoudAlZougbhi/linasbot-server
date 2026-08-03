#!/usr/bin/env python3
"""Validate the new Page token and linked Instagram identity without printing tokens."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import cast

EXPECTED_PAGE_ID = "378696005334409"
EXPECTED_INSTAGRAM_ID = "17841413184256533"
RETIRED_APP_ID = "1784792718776344"
EXPECTED_GRAPH_VERSION = "v24.0"
EXPECTED_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"
EXPECTED_WEBHOOK_FIELDS = {"messages", "messaging_postbacks"}
REQUIRED_SCOPES = {
    "pages_messaging",
    "pages_manage_metadata",
    "pages_show_list",
    "pages_read_engagement",
    "instagram_basic",
    "instagram_manage_messages",
}


class MetaTokenValidationError(RuntimeError):
    """Raised when Graph metadata does not match the one approved integration."""


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _subscription_field_names(value: object) -> set[str]:
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


def validate_debug_payload(
    debug_payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Validate token metadata before making any Page data request."""

    if not expected_app_id.isdigit() or expected_app_id == RETIRED_APP_ID:
        raise MetaTokenValidationError("New App ID is missing, malformed, or belongs to the retired app")
    data = _mapping(debug_payload.get("data"))
    scopes_raw = data.get("scopes")
    scopes = {str(item) for item in scopes_raw} if isinstance(scopes_raw, list) else set()

    target_ids: set[str] = set()
    granular_raw = data.get("granular_scopes")
    if isinstance(granular_raw, list):
        for item in granular_raw:
            granular = _mapping(item)
            raw_targets = granular.get("target_ids")
            if isinstance(raw_targets, list):
                target_ids.update(str(target) for target in raw_targets)

    checks = {
        "token_valid": data.get("is_valid") is True,
        "token_app_id_match": str(data.get("app_id") or "") == expected_app_id,
        "token_type_is_page": str(data.get("type") or "").upper() == "PAGE",
        "token_has_no_expiry": data.get("expires_at") == 0,
        "granular_targets_present": EXPECTED_PAGE_ID in target_ids,
        "granular_targets_allowlisted": bool(target_ids)
        and target_ids.issubset({EXPECTED_PAGE_ID, EXPECTED_INSTAGRAM_ID}),
    }
    checks.update({f"scope_{scope}_present": scope in scopes for scope in sorted(REQUIRED_SCOPES)})
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(f"Meta Page token debug validation failed checks={failed}")
    return checks


def validate_payloads(
    debug_payload: dict[str, object],
    profile_payload: dict[str, object],
    page_payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Return boolean-only checks or fail without rendering any credential."""

    checks = validate_debug_payload(debug_payload, expected_app_id=expected_app_id)
    instagram = _mapping(page_payload.get("instagram_business_account"))
    checks.update(
        {
            "token_profile_is_target_page": str(profile_payload.get("id") or "") == EXPECTED_PAGE_ID,
            "page_query_is_target_page": str(page_payload.get("id") or "") == EXPECTED_PAGE_ID,
            "instagram_relationship_match": str(instagram.get("id") or "") == EXPECTED_INSTAGRAM_ID,
        }
    )
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(f"Meta Page token validation failed checks={failed}")
    return checks


def validate_conversation_payloads(
    messenger_payload: dict[str, object],
    instagram_payload: dict[str, object],
) -> dict[str, bool]:
    """Prove both messaging APIs are callable without rendering conversation data."""

    checks = {
        "messenger_conversations_query_succeeded": isinstance(messenger_payload.get("data"), list),
        "instagram_conversations_query_succeeded": isinstance(instagram_payload.get("data"), list),
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(f"Meta conversation validation failed checks={failed}")
    return checks


def validate_page_subscription_payload(
    payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Require one installed messaging app with the exact DM-only webhook fields."""

    raw_apps = payload.get("data")
    apps = raw_apps if isinstance(raw_apps, list) else []
    app = _mapping(apps[0]) if len(apps) == 1 else {}
    raw_fields = app.get("subscribed_fields")
    fields = _subscription_field_names(raw_fields)
    checks = {
        "page_has_single_subscribed_app": len(apps) == 1,
        "page_subscribed_app_id_match": str(app.get("id") or "") == expected_app_id,
        "page_subscribed_fields_dm_only": fields == EXPECTED_WEBHOOK_FIELDS,
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(f"Meta Page subscription validation failed checks={failed}")
    return checks


def validate_instagram_subscription_payload(
    payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Require the linked Instagram account to install only the dedicated app's DM fields."""

    raw_apps = payload.get("data")
    apps = raw_apps if isinstance(raw_apps, list) else []
    app = _mapping(apps[0]) if len(apps) == 1 else {}
    fields = _subscription_field_names(app.get("subscribed_fields"))
    checks = {
        "instagram_has_single_subscribed_app": len(apps) == 1,
        "instagram_subscribed_app_id_match": str(app.get("id") or "") == expected_app_id,
        "instagram_subscribed_fields_dm_only": fields == EXPECTED_WEBHOOK_FIELDS,
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(f"Meta Instagram subscription validation failed checks={failed}")
    return checks


def validate_app_webhook_payload(payload: dict[str, object]) -> dict[str, bool]:
    """Require active Page and Instagram callbacks with only DM webhook fields."""

    raw_subscriptions = payload.get("data")
    subscriptions = raw_subscriptions if isinstance(raw_subscriptions, list) else []
    by_object = {
        str(subscription.get("object") or "").strip().lower(): subscription
        for subscription in subscriptions
        if isinstance(subscription, dict)
    }
    page = _mapping(by_object.get("page"))
    instagram = _mapping(by_object.get("instagram"))
    checks = {
        "app_webhook_objects_dm_only": set(by_object) == {"page", "instagram"},
        "app_page_webhook_active": page.get("active") is True,
        "app_page_webhook_callback_match": str(page.get("callback_url") or "") == EXPECTED_CALLBACK_URL,
        "app_page_webhook_fields_dm_only": _subscription_field_names(page.get("fields")) == EXPECTED_WEBHOOK_FIELDS,
        "app_instagram_webhook_active": instagram.get("active") is True,
        "app_instagram_webhook_callback_match": str(instagram.get("callback_url") or "") == EXPECTED_CALLBACK_URL,
        "app_instagram_webhook_fields_dm_only": _subscription_field_names(instagram.get("fields"))
        == EXPECTED_WEBHOOK_FIELDS,
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(f"Meta app webhook validation failed checks={failed}")
    return checks


def _request_json(url: str, *, bearer: str | None = None) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            decoded: object = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise MetaTokenValidationError(f"Meta Graph request returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise MetaTokenValidationError("Meta Graph request failed") from None
    if not isinstance(decoded, dict):
        raise MetaTokenValidationError("Meta Graph response was not an object")
    return cast(dict[str, object], decoded)


def main() -> None:
    app_id = (os.environ.get("META_APP_ID") or "").strip()
    app_secret = (os.environ.get("META_APP_SECRET") or "").strip()
    page_token = (os.environ.get("META_PAGE_ACCESS_TOKEN") or "").strip()
    version = (os.environ.get("META_GRAPH_API_VERSION") or "").strip()
    if not app_id or not app_secret or not page_token:
        raise MetaTokenValidationError("Required Meta credential variables are missing")
    if version != EXPECTED_GRAPH_VERSION:
        raise MetaTokenValidationError("Unexpected Meta Graph API version")

    base = f"https://graph.facebook.com/{version}"
    debug_query = urllib.parse.urlencode(
        {
            "input_token": page_token,
            "access_token": f"{app_id}|{app_secret}",
        }
    )
    debug_payload = _request_json(f"{base}/debug_token?{debug_query}")
    validate_debug_payload(debug_payload, expected_app_id=app_id)
    page_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}?fields=id,instagram_business_account{{id}}",
        bearer=page_token,
    )
    checks = validate_payloads(
        debug_payload,
        page_payload,
        page_payload,
        expected_app_id=app_id,
    )
    messenger_query = urllib.parse.urlencode({"fields": "id", "limit": "1"})
    instagram_query = urllib.parse.urlencode({"fields": "id", "limit": "1", "platform": "instagram"})
    messenger_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}/conversations?{messenger_query}",
        bearer=page_token,
    )
    instagram_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}/conversations?{instagram_query}",
        bearer=page_token,
    )
    checks.update(validate_conversation_payloads(messenger_payload, instagram_payload))
    subscription_query = urllib.parse.urlencode({"fields": "id,subscribed_fields"})
    subscription_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}/subscribed_apps?{subscription_query}",
        bearer=page_token,
    )
    checks.update(validate_page_subscription_payload(subscription_payload, expected_app_id=app_id))
    instagram_subscription_payload = _request_json(
        f"{base}/{EXPECTED_INSTAGRAM_ID}/subscribed_apps?{subscription_query}",
        bearer=page_token,
    )
    checks.update(
        validate_instagram_subscription_payload(
            instagram_subscription_payload,
            expected_app_id=app_id,
        )
    )
    app_subscription_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    app_subscription_payload = _request_json(
        f"{base}/{app_id}/subscriptions?{app_subscription_query}",
        bearer=f"{app_id}|{app_secret}",
    )
    checks.update(validate_app_webhook_payload(app_subscription_payload))
    for name in sorted(checks):
        print(f"[meta-token] {name}=true")
    print(f"[meta-token] page_id={EXPECTED_PAGE_ID}")
    print(f"[meta-token] instagram_account_id={EXPECTED_INSTAGRAM_ID}")
    print("[meta-token] SUCCESS")


if __name__ == "__main__":
    main()
