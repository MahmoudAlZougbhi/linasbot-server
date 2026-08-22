"""Pure Meta webhook field contracts shared by validation and reconcile scripts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

DM_WEBHOOK_FIELDS = frozenset({"messages", "messaging_postbacks"})
PAGE_SUBSCRIPTION_DM_ONLY = frozenset({"messages", "messaging_postbacks", "standby"})
PAGE_SUBSCRIPTION_COMMENT_DELIVERY = frozenset({"feed", "messages", "messaging_postbacks", "standby"})
ALLOWED_PAGE_SUBSCRIPTION_FIELDS = PAGE_SUBSCRIPTION_COMMENT_DELIVERY
APP_PAGE_WEBHOOK_FIELDS = PAGE_SUBSCRIPTION_COMMENT_DELIVERY
APP_INSTAGRAM_WEBHOOK_FIELDS = frozenset({"comments", "messages", "messaging_postbacks"})

FACEBOOK_COMMENT_SCOPES = frozenset({"pages_read_user_content", "pages_manage_engagement"})
INSTAGRAM_COMMENT_SCOPES = frozenset({"instagram_manage_comments"})
PUBLISH_FEATURE_SCOPES = frozenset({"pages_manage_posts", "instagram_content_publish"})
COMMENT_FEATURE_SCOPES = FACEBOOK_COMMENT_SCOPES | INSTAGRAM_COMMENT_SCOPES


@dataclass(frozen=True)
class FieldSetCheck:
    exact: bool
    dm_fields_present: bool
    missing_fields: tuple[str, ...]
    extra_fields: tuple[str, ...]


def parse_bool_env(value: str | None, *, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _mapping(value: object) -> dict[str, object]:
    return cast(dict[str, object], value) if isinstance(value, dict) else {}


def subscription_field_names(value: object) -> set[str]:
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


def extract_page_subscribed_fields(payload: dict[str, object]) -> set[str]:
    raw_apps = payload.get("data")
    apps = raw_apps if isinstance(raw_apps, list) else []
    app = _mapping(apps[0]) if len(apps) == 1 else {}
    return subscription_field_names(app.get("subscribed_fields"))


def extract_page_subscribed_app_id(payload: dict[str, object]) -> str:
    raw_apps = payload.get("data")
    apps = raw_apps if isinstance(raw_apps, list) else []
    app = _mapping(apps[0]) if len(apps) == 1 else {}
    return str(app.get("id") or "")


def page_subscribed_app_count(payload: dict[str, object]) -> int:
    raw_apps = payload.get("data")
    apps = raw_apps if isinstance(raw_apps, list) else []
    return len(apps)


def check_exact_fields(actual: set[str], expected: frozenset[str]) -> FieldSetCheck:
    missing = tuple(sorted(expected - actual))
    extra = tuple(sorted(actual - expected))
    return FieldSetCheck(
        exact=not missing and not extra,
        dm_fields_present=DM_WEBHOOK_FIELDS.issubset(actual),
        missing_fields=missing,
        extra_fields=extra,
    )


def merge_subscription_fields(current: set[str], required: frozenset[str]) -> set[str]:
    merged = set(current) | set(required)
    if not DM_WEBHOOK_FIELDS.issubset(merged):
        raise ValueError("DM webhook fields would be removed")
    return merged


def plan_page_subscription_reconcile(current: set[str]) -> set[str]:
    """Idempotently merge Page subscribed fields for Facebook comment delivery."""

    return merge_subscription_fields(current, PAGE_SUBSCRIPTION_COMMENT_DELIVERY)


def validate_page_subscription_baseline(
    payload: dict[str, object],
    *,
    expected_app_id: str,
) -> dict[str, bool]:
    """Require DM fields as a subset; feed presence must not fail baseline."""

    app_count = page_subscribed_app_count(payload)
    app_id = extract_page_subscribed_app_id(payload)
    fields = extract_page_subscribed_fields(payload)
    checks = {
        "page_has_single_subscribed_app": app_count == 1,
        "page_subscribed_app_id_match": app_id == expected_app_id,
        "page_subscribed_dm_fields_present": DM_WEBHOOK_FIELDS.issubset(fields),
    }
    return checks


def assert_page_subscription_baseline(
    payload: dict[str, object],
    *,
    expected_app_id: str,
    error_type: type[Exception],
) -> dict[str, bool]:
    checks = validate_page_subscription_baseline(payload, expected_app_id=expected_app_id)
    if not all(checks.values()):
        failed = sorted(key for key, value in checks.items() if not value)
        fields = extract_page_subscribed_fields(payload)
        raise error_type(
            "Meta Page subscription baseline failed "
            f"checks={failed} subscribed_fields={sorted(fields)} "
            f"subscribed_fields_missing={sorted(DM_WEBHOOK_FIELDS - fields)}"
        )
    return checks


def validate_page_subscription_configuration(
    payload: dict[str, object],
    *,
    expected_app_id: str,
    expect_facebook_comment_delivery: bool,
) -> dict[str, bool]:
    """Validate Page subscription profile for the current explicit delivery mode."""

    fields = extract_page_subscribed_fields(payload)
    forbidden_extra = tuple(sorted(fields - ALLOWED_PAGE_SUBSCRIPTION_FIELDS))
    dm_check = check_exact_fields(fields, DM_WEBHOOK_FIELDS)
    comment_core = frozenset({"feed"}) | DM_WEBHOOK_FIELDS
    delivery_ready = comment_core.issubset(fields) and fields.issubset(ALLOWED_PAGE_SUBSCRIPTION_FIELDS)
    allowed_profiles = {
        DM_WEBHOOK_FIELDS,
        PAGE_SUBSCRIPTION_DM_ONLY,
        comment_core,
        PAGE_SUBSCRIPTION_COMMENT_DELIVERY,
    }
    checks = {
        "page_has_single_subscribed_app": page_subscribed_app_count(payload) == 1,
        "page_subscribed_app_id_match": extract_page_subscribed_app_id(payload) == expected_app_id,
        "page_subscribed_dm_fields_present": dm_check.dm_fields_present,
        "page_subscribed_forbidden_fields_absent": not forbidden_extra,
        "facebook_comment_delivery_infrastructure_ready": delivery_ready,
        "facebook_comment_delivery_profile_matches_expectation": (
            delivery_ready if expect_facebook_comment_delivery else fields in allowed_profiles
        ),
    }
    return checks


def assert_page_subscription_configuration(
    payload: dict[str, object],
    *,
    expected_app_id: str,
    expect_facebook_comment_delivery: bool,
    error_type: type[Exception],
) -> dict[str, bool]:
    checks = validate_page_subscription_configuration(
        payload,
        expected_app_id=expected_app_id,
        expect_facebook_comment_delivery=expect_facebook_comment_delivery,
    )
    fields = extract_page_subscribed_fields(payload)
    forbidden_extra = tuple(sorted(fields - ALLOWED_PAGE_SUBSCRIPTION_FIELDS))
    if forbidden_extra:
        raise error_type(
            "Meta Page subscription configuration failed "
            f"subscribed_fields_extra={list(forbidden_extra)} subscribed_fields={sorted(fields)}"
        )
    if not DM_WEBHOOK_FIELDS.issubset(fields):
        raise error_type(
            "Meta Page subscription configuration failed "
            f"subscribed_fields_missing={sorted(DM_WEBHOOK_FIELDS - fields)}"
        )
    if expect_facebook_comment_delivery:
        comment_core = frozenset({"feed"}) | DM_WEBHOOK_FIELDS
        if not comment_core.issubset(fields):
            raise error_type(
                "Meta Page subscription configuration failed "
                f"expect_facebook_comment_delivery=true "
                f"subscribed_fields_missing={sorted(comment_core - fields)} "
                f"subscribed_fields_extra={sorted(fields - ALLOWED_PAGE_SUBSCRIPTION_FIELDS)}"
            )
    elif fields not in {
        DM_WEBHOOK_FIELDS,
        PAGE_SUBSCRIPTION_DM_ONLY,
        frozenset({"feed"}) | DM_WEBHOOK_FIELDS,
        PAGE_SUBSCRIPTION_COMMENT_DELIVERY,
    }:
        raise error_type(
            "Meta Page subscription configuration failed "
            f"expect_facebook_comment_delivery=false invalid_profile={sorted(fields)}"
        )
    failing = {
        key: value
        for key, value in checks.items()
        if not value and key != "facebook_comment_delivery_infrastructure_ready"
    }
    if failing:
        failed = sorted(failing)
        raise error_type(f"Meta Page subscription configuration failed checks={failed}")
    return checks


def evaluate_feature_readiness(
    *,
    scopes: set[str],
    app_page_fields: set[str],
    app_instagram_fields: set[str],
    page_subscribed_fields: set[str],
    facebook_comment_switch_enabled: bool,
    instagram_comment_switch_enabled: bool,
) -> dict[str, bool]:
    """Informational readiness only; never fails validation when features are disabled."""

    app_page_ready = (frozenset({"feed"}) | DM_WEBHOOK_FIELDS).issubset(app_page_fields) and app_page_fields.issubset(
        APP_PAGE_WEBHOOK_FIELDS
    )
    app_instagram_check = check_exact_fields(app_instagram_fields, APP_INSTAGRAM_WEBHOOK_FIELDS)
    page_delivery_ready = (frozenset({"feed"}) | DM_WEBHOOK_FIELDS).issubset(
        page_subscribed_fields
    ) and page_subscribed_fields.issubset(ALLOWED_PAGE_SUBSCRIPTION_FIELDS)

    facebook_scopes_ready = FACEBOOK_COMMENT_SCOPES.issubset(scopes)
    instagram_scopes_ready = INSTAGRAM_COMMENT_SCOPES.issubset(scopes)
    publish_scopes_ready = PUBLISH_FEATURE_SCOPES.issubset(scopes)

    facebook_comments_ready = (
        facebook_scopes_ready and app_page_ready and page_delivery_ready and facebook_comment_switch_enabled
    )
    instagram_comments_ready = (
        instagram_scopes_ready
        and app_instagram_check.exact
        and app_instagram_check.dm_fields_present
        and instagram_comment_switch_enabled
    )

    readiness: dict[str, bool] = {
        "facebook_comment_delivery_infrastructure_ready": page_delivery_ready and app_page_ready,
        "facebook_comments_ready": facebook_comments_ready,
        "instagram_comments_ready": instagram_comments_ready,
        "publish_features_ready": publish_scopes_ready,
        "facebook_comment_switch_enabled": facebook_comment_switch_enabled,
        "instagram_comment_switch_enabled": instagram_comment_switch_enabled,
    }
    for scope in sorted(FACEBOOK_COMMENT_SCOPES | INSTAGRAM_COMMENT_SCOPES | PUBLISH_FEATURE_SCOPES):
        readiness[f"scope_{scope}_present"] = scope in scopes
    return readiness
