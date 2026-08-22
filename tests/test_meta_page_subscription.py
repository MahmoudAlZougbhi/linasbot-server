"""Safety contracts for the one-Page Meta subscription controller."""

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.manage_meta_page_subscription import (
    MetaConfig,
    MetaSubscriptionError,
    load_config,
    plan_subscription_reconcile,
    subscribe,
    validate_state,
)


def _payload(app_id: str = "2963733803971681", fields: list[str] | None = None) -> dict[str, object]:
    return {
        "data": [
            {
                "id": app_id,
                "subscribed_fields": fields or ["messages", "messaging_postbacks"],
            }
        ]
    }


def test_dm_only_current_app_is_incomplete() -> None:
    with pytest.raises(MetaSubscriptionError):
        validate_state(_payload(), current_app_id="2963733803971681", expectation="current-only")


def test_feed_plus_dm_fields_are_accepted() -> None:
    app_ids, fields = validate_state(
        _payload(fields=["feed", "messages", "messaging_postbacks", "standby"]),
        current_app_id="2963733803971681",
        expectation="current-only",
    )

    assert app_ids == {"2963733803971681"}
    assert fields == ("feed", "messages", "messaging_postbacks", "standby")


def test_subscription_reconcile_preserves_feed_when_repairing_dm_fields() -> None:
    assert plan_subscription_reconcile(("feed",)) == (
        "feed",
        "messages",
        "messaging_postbacks",
        "standby",
    )


def test_subscription_reconcile_adds_feed_to_dm_only_state() -> None:
    assert plan_subscription_reconcile(("messages", "messaging_postbacks")) == (
        "feed",
        "messages",
        "messaging_postbacks",
        "standby",
    )


def test_subscribe_posts_merged_fields_when_feed_is_already_present() -> None:
    config = MetaConfig(
        app_id="2963733803971681",
        page_id="378696005334409",
        instagram_id="17841413184256533",
        graph_version="v24.0",
        page_token="page-token",
    )
    before = _payload(fields=["feed"])
    after = _payload(fields=["feed", "messages", "messaging_postbacks", "standby"])

    with (
        patch("scripts.manage_meta_page_subscription._status", side_effect=[before, after]),
        patch(
            "scripts.manage_meta_page_subscription._request_json",
            return_value={"success": True},
        ) as request_json,
    ):
        subscribe(config, allow_present=False)

    assert request_json.call_args.kwargs["form"] == {"subscribed_fields": "feed,messages,messaging_postbacks,standby"}


@pytest.mark.parametrize(
    ("payload", "expectation"),
    [
        ({"data": []}, "current-only"),
        (_payload("1784792718776344"), "current-only"),
        (
            {
                "data": [
                    {
                        "id": "2963733803971681",
                        "subscribed_fields": ["messages", "messaging_postbacks"],
                    },
                    {"id": "999999999999999", "subscribed_fields": ["messages"]},
                ]
            },
            "current-only",
        ),
        (_payload(fields=["feed", "messages"]), "current-only"),
        (_payload(fields=["mentions", "messages", "messaging_postbacks"]), "current-only"),
        (_payload(), "empty"),
    ],
)
def test_unexpected_app_or_field_state_is_rejected(payload: dict[str, object], expectation: str) -> None:
    with pytest.raises(MetaSubscriptionError):
        validate_state(payload, current_app_id="2963733803971681", expectation=expectation)


def test_empty_state_is_accepted_only_when_explicit() -> None:
    app_ids, fields = validate_state({"data": []}, current_app_id="2963733803971681", expectation="empty")
    assert not app_ids
    assert not fields


def test_config_loader_enforces_all_asset_and_version_boundaries(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "META_APP_ID=2963733803971681",
                "META_PAGE_ID=378696005334409",
                "META_INSTAGRAM_ACCOUNT_ID=17841413184256533",
                "META_GRAPH_API_VERSION=v24.0",
                "META_PAGE_ACCESS_TOKEN=secret-placeholder-not-a-real-token",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(env_file)
    assert config.app_id == "2963733803971681"
    assert config.page_id == "378696005334409"
    assert config.instagram_id == "17841413184256533"

    env_file.write_text(env_file.read_text().replace("v24.0", "v26.0"), encoding="utf-8")
    with pytest.raises(MetaSubscriptionError):
        load_config(env_file)

    env_file.write_text(
        env_file.read_text().replace("v26.0", "v24.0").replace("2963733803971681", "999999999"),
        encoding="utf-8",
    )
    with pytest.raises(MetaSubscriptionError, match="unexpected Meta App ID"):
        load_config(env_file)


def test_retired_app_mode_is_exactly_allowlisted_and_requires_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "META_APP_ID=1784792718776344",
                "META_PAGE_ID=378696005334409",
                "META_INSTAGRAM_ACCOUNT_ID=17841413184256533",
                "META_GRAPH_API_VERSION=v24.0",
                "META_PAGE_ACCESS_TOKEN=retired-placeholder-not-a-real-token",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(MetaSubscriptionError, match="explicit confirmation"):
        load_config(env_file, expected_app_id="1784792718776344")

    monkeypatch.setenv(
        "META_RETIRED_APP_SUBSCRIPTION_CONFIRM",
        "CONFIRM_RETIRED_META_APP_SUBSCRIPTION",
    )
    assert load_config(env_file, expected_app_id="1784792718776344").app_id == "1784792718776344"

    with pytest.raises(MetaSubscriptionError, match="exact cutover allowlist"):
        load_config(env_file, expected_app_id="999999999999999")
