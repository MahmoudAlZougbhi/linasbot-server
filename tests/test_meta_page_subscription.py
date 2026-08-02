"""Safety contracts for the one-Page Meta subscription controller."""

from pathlib import Path

import pytest

from scripts.manage_meta_page_subscription import (
    MetaSubscriptionError,
    load_config,
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


def test_exact_current_app_and_fields_are_accepted() -> None:
    app_ids, fields = validate_state(_payload(), current_app_id="2963733803971681", expectation="current-only")
    assert app_ids == {"2963733803971681"}
    assert fields == ("messages", "messaging_postbacks")


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
