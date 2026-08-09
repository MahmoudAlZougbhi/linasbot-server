#!/usr/bin/env python3
"""Validate Meta App A DM baseline, webhook configuration, and feature readiness."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import cast

from scripts.meta_webhook_contract import (
    APP_INSTAGRAM_WEBHOOK_FIELDS,
    APP_PAGE_WEBHOOK_FIELDS,
    COMMENT_FEATURE_SCOPES,
    DM_WEBHOOK_FIELDS,
    FACEBOOK_COMMENT_SCOPES,
    INSTAGRAM_COMMENT_SCOPES,
    PUBLISH_FEATURE_SCOPES,
    assert_page_subscription_baseline,
    assert_page_subscription_configuration,
    check_exact_fields,
    evaluate_feature_readiness,
    extract_page_subscribed_fields,
    parse_bool_env,
    subscription_field_names,
)

__all__ = [
    "APP_INSTAGRAM_WEBHOOK_FIELDS",
    "APP_PAGE_WEBHOOK_FIELDS",
    "COMMENT_FEATURE_SCOPES",
    "DM_WEBHOOK_FIELDS",
    "FACEBOOK_COMMENT_SCOPES",
    "INSTAGRAM_COMMENT_SCOPES",
    "PUBLISH_FEATURE_SCOPES",
    "MetaTokenValidationError",
    "evaluate_feature_readiness",
    "validate_app_webhook_configuration",
    "validate_conversation_payloads",
    "validate_page_subscription_baseline",
    "validate_page_subscription_configuration",
    "validate_page_subscription_payload",
    "validate_payloads",
]

EXPECTED_PAGE_ID = "378696005334409"
EXPECTED_INSTAGRAM_ID = "17841413184256533"
RETIRED_APP_ID = "1784792718776344"
EXPECTED_GRAPH_VERSION = "v24.0"
EXPECTED_CALLBACK_URL = "https://www.linasaibot.com/webhook/meta-messaging"

REQUIRED_SCOPES = frozenset(
    {
        "pages_messaging",
        "pages_manage_metadata",
        "pages_show_list",
        "pages_read_engagement",
        "instagram_basic",
        "instagram_manage_messages",
    }
)


class MetaTokenValidationError(RuntimeError):
    """Raised when baseline DM health or webhook configuration is invalid."""


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def _scopes_from_debug_payload(debug_payload: dict[str, object]) -> set[str]:
    data = _mapping(debug_payload.get("data"))
    scopes_raw = data.get("scopes")
    if not isinstance(scopes_raw, list):
        return set()
    return {str(item) for item in scopes_raw}


def validate_debug_payload(
    debug_payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Validate DM baseline token metadata before making any Page data request."""

    if not expected_app_id.isdigit() or expected_app_id == RETIRED_APP_ID:
        raise MetaTokenValidationError("New App ID is missing, malformed, or belongs to the retired app")
    data = _mapping(debug_payload.get("data"))
    scopes = _scopes_from_debug_payload(debug_payload)

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
    """Return boolean-only baseline checks or fail without rendering any credential."""

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


def validate_page_subscription_baseline(
    payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Require Page subscribed_apps to preserve DM fields; feed must not fail baseline."""

    return assert_page_subscription_baseline(
        payload,
        expected_app_id=expected_app_id,
        error_type=MetaTokenValidationError,
    )


def validate_page_subscription_configuration(
    payload: dict[str, object],
    *,
    expected_app_id: str,
    expect_facebook_comment_delivery: bool,
) -> dict[str, bool]:
    """Validate Page subscription profile for the explicit delivery mode."""

    return assert_page_subscription_configuration(
        payload,
        expected_app_id=expected_app_id,
        expect_facebook_comment_delivery=expect_facebook_comment_delivery,
        error_type=MetaTokenValidationError,
    )


def validate_page_subscription_payload(
    payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Backward-compatible alias for baseline Page subscription validation."""

    return validate_page_subscription_baseline(payload, expected_app_id=expected_app_id)


def validate_app_webhook_configuration(payload: dict[str, object]) -> dict[str, bool]:
    """Require active Page and Instagram callbacks with exact app-level webhook fields."""

    raw_subscriptions = payload.get("data")
    subscriptions = raw_subscriptions if isinstance(raw_subscriptions, list) else []
    by_object = {
        str(subscription.get("object") or "").strip().lower(): subscription
        for subscription in subscriptions
        if isinstance(subscription, dict)
    }
    page = _mapping(by_object.get("page"))
    instagram = _mapping(by_object.get("instagram"))
    page_fields = subscription_field_names(page.get("fields"))
    instagram_fields = subscription_field_names(instagram.get("fields"))
    page_field_check = check_exact_fields(page_fields, APP_PAGE_WEBHOOK_FIELDS)
    instagram_field_check = check_exact_fields(instagram_fields, APP_INSTAGRAM_WEBHOOK_FIELDS)
    checks = {
        "app_webhook_objects_exact": set(by_object) == {"page", "instagram"},
        "app_page_webhook_active": page.get("active") is True,
        "app_page_webhook_callback_match": str(page.get("callback_url") or "") == EXPECTED_CALLBACK_URL,
        "app_page_webhook_fields_exact": page_field_check.exact,
        "app_page_webhook_dm_fields_present": page_field_check.dm_fields_present,
        "app_instagram_webhook_active": instagram.get("active") is True,
        "app_instagram_webhook_callback_match": str(instagram.get("callback_url") or "") == EXPECTED_CALLBACK_URL,
        "app_instagram_webhook_fields_exact": instagram_field_check.exact,
        "app_instagram_webhook_dm_fields_present": instagram_field_check.dm_fields_present,
    }
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        raise MetaTokenValidationError(
            "Meta app webhook configuration failed "
            f"checks={failed} "
            f"page_fields={sorted(page_fields)} "
            f"page_fields_missing={list(page_field_check.missing_fields)} "
            f"page_fields_extra={list(page_field_check.extra_fields)} "
            f"instagram_fields={sorted(instagram_fields)} "
            f"instagram_fields_missing={list(instagram_field_check.missing_fields)} "
            f"instagram_fields_extra={list(instagram_field_check.extra_fields)}"
        )
    return checks


def validate_app_webhook_payload(payload: dict[str, object]) -> dict[str, bool]:
    """Backward-compatible alias for app webhook configuration validation."""

    return validate_app_webhook_configuration(payload)


def _request_json(
    url: str,
    *,
    bearer: str | None = None,
    stage: str,
) -> dict[str, object]:
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            decoded: object = json.loads(response.read(1_000_000))
    except urllib.error.HTTPError as exc:
        raise MetaTokenValidationError(f"Meta Graph request failed stage={stage} http={exc.code}") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise MetaTokenValidationError(f"Meta Graph request failed stage={stage}") from None
    if not isinstance(decoded, dict):
        raise MetaTokenValidationError(f"Meta Graph response was not an object stage={stage}")
    return cast(dict[str, object], decoded)


def _print_checks(section: str, checks: dict[str, bool]) -> None:
    for name in sorted(checks):
        print(f"[meta-token][{section}] {name}={str(checks[name]).lower()}")


def _validation_expectations_from_env() -> tuple[bool, bool, bool]:
    expect_delivery = parse_bool_env(os.environ.get("META_EXPECT_FACEBOOK_COMMENT_DELIVERY"), default=False)
    facebook_switch = parse_bool_env(os.environ.get("META_FACEBOOK_COMMENT_SWITCH_ENABLED"), default=False)
    instagram_switch = parse_bool_env(os.environ.get("META_INSTAGRAM_COMMENT_SWITCH_ENABLED"), default=False)
    return expect_delivery, facebook_switch, instagram_switch


def main() -> None:
    app_id = (os.environ.get("META_APP_ID") or "").strip()
    app_secret = (os.environ.get("META_APP_SECRET") or "").strip()
    page_token = (os.environ.get("META_PAGE_ACCESS_TOKEN") or "").strip()
    version = (os.environ.get("META_GRAPH_API_VERSION") or "").strip()
    if not app_id or not app_secret or not page_token:
        raise MetaTokenValidationError("Required Meta credential variables are missing")
    if version != EXPECTED_GRAPH_VERSION:
        raise MetaTokenValidationError("Unexpected Meta Graph API version")

    expect_facebook_comment_delivery, facebook_switch_enabled, instagram_switch_enabled = (
        _validation_expectations_from_env()
    )

    base = f"https://graph.facebook.com/{version}"
    debug_query = urllib.parse.urlencode(
        {
            "input_token": page_token,
            "access_token": f"{app_id}|{app_secret}",
        }
    )
    debug_payload = _request_json(f"{base}/debug_token?{debug_query}", stage="debug_token")
    page_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}?fields=id,instagram_business_account{{id}}",
        bearer=page_token,
        stage="page_relationship",
    )

    baseline_checks: dict[str, bool] = {}
    baseline_checks.update(validate_payloads(debug_payload, page_payload, page_payload, expected_app_id=app_id))

    messenger_query = urllib.parse.urlencode({"fields": "id", "limit": "1"})
    instagram_query = urllib.parse.urlencode({"fields": "id", "limit": "1", "platform": "instagram"})
    messenger_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}/conversations?{messenger_query}",
        bearer=page_token,
        stage="messenger_conversations",
    )
    instagram_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}/conversations?{instagram_query}",
        bearer=page_token,
        stage="instagram_conversations",
    )
    baseline_checks.update(validate_conversation_payloads(messenger_payload, instagram_payload))

    subscription_query = urllib.parse.urlencode({"fields": "id,subscribed_fields"})
    subscription_payload = _request_json(
        f"{base}/{EXPECTED_PAGE_ID}/subscribed_apps?{subscription_query}",
        bearer=page_token,
        stage="page_subscribed_apps",
    )
    baseline_checks.update(validate_page_subscription_baseline(subscription_payload, expected_app_id=app_id))

    page_subscription_checks = validate_page_subscription_configuration(
        subscription_payload,
        expected_app_id=app_id,
        expect_facebook_comment_delivery=expect_facebook_comment_delivery,
    )

    app_subscription_query = urllib.parse.urlencode({"fields": "object,callback_url,active,fields"})
    app_subscription_payload = _request_json(
        f"{base}/{app_id}/subscriptions?{app_subscription_query}",
        bearer=f"{app_id}|{app_secret}",
        stage="app_subscriptions",
    )
    app_webhook_checks = validate_app_webhook_configuration(app_subscription_payload)

    raw_subscriptions = app_subscription_payload.get("data")
    subscriptions = raw_subscriptions if isinstance(raw_subscriptions, list) else []
    by_object = {
        str(subscription.get("object") or "").strip().lower(): subscription
        for subscription in subscriptions
        if isinstance(subscription, dict)
    }
    page_fields = subscription_field_names(_mapping(by_object.get("page")).get("fields"))
    instagram_fields = subscription_field_names(_mapping(by_object.get("instagram")).get("fields"))

    feature_readiness = evaluate_feature_readiness(
        scopes=_scopes_from_debug_payload(debug_payload),
        app_page_fields=page_fields,
        app_instagram_fields=instagram_fields,
        page_subscribed_fields=extract_page_subscribed_fields(subscription_payload),
        facebook_comment_switch_enabled=facebook_switch_enabled,
        instagram_comment_switch_enabled=instagram_switch_enabled,
    )

    _print_checks("baseline-dm", baseline_checks)
    _print_checks("page-subscription", page_subscription_checks)
    _print_checks("app-webhooks", app_webhook_checks)
    _print_checks("feature-readiness", feature_readiness)

    print(f"[meta-token] page_id={EXPECTED_PAGE_ID}")
    print(f"[meta-token] instagram_account_id={EXPECTED_INSTAGRAM_ID}")
    print("[meta-token] expect_facebook_comment_delivery=" + str(expect_facebook_comment_delivery).lower())
    print("[meta-token] expected_app_page_fields=" + ",".join(sorted(APP_PAGE_WEBHOOK_FIELDS)))
    print("[meta-token] expected_app_instagram_fields=" + ",".join(sorted(APP_INSTAGRAM_WEBHOOK_FIELDS)))
    print("[meta-token] baseline_dm_health=true")
    print("[meta-token] app_webhook_configuration=true")
    print("[meta-token] page_subscription_configuration=true")
    print("[meta-token] SUCCESS")


if __name__ == "__main__":
    main()
