"""Strict allowlist tests for new-app Page token metadata."""

import pytest

from scripts.validate_meta_social_token import MetaTokenValidationError, validate_payloads


def _valid_payloads() -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    return (
        {
            "data": {
                "is_valid": True,
                "app_id": "999000111222333",
                "type": "PAGE",
                "scopes": [
                    "pages_messaging",
                    "pages_manage_metadata",
                    "pages_show_list",
                    "pages_read_engagement",
                    "instagram_basic",
                    "instagram_manage_messages",
                ],
                "granular_scopes": [
                    {
                        "scope": "pages_messaging",
                        "target_ids": ["378696005334409"],
                    },
                    {
                        "scope": "instagram_manage_messages",
                        "target_ids": ["17841413184256533"],
                    },
                ],
            }
        },
        {"id": "378696005334409"},
        {
            "id": "378696005334409",
            "instagram_business_account": {"id": "17841413184256533"},
        },
    )


def test_exact_page_instagram_app_scopes_and_targets_pass() -> None:
    debug, profile, page = _valid_payloads()
    checks = validate_payloads(debug, profile, page, expected_app_id="999000111222333")
    assert all(checks.values())


@pytest.mark.parametrize("failure", ["old_app", "wrong_page", "wrong_instagram", "extra_target", "missing_scope"])
def test_unexpected_token_identity_or_access_fails(failure: str) -> None:
    debug, profile, page = _valid_payloads()
    app_id = "999000111222333"
    if failure == "old_app":
        app_id = "1784792718776344"
    elif failure == "wrong_page":
        profile["id"] = "999999999999999"
    elif failure == "wrong_instagram":
        page["instagram_business_account"] = {"id": "99999999999999999"}
    elif failure == "extra_target":
        data = debug["data"]
        assert isinstance(data, dict)
        granular = data["granular_scopes"]
        assert isinstance(granular, list)
        granular.append({"scope": "pages_messaging", "target_ids": ["999999999999999"]})
    else:
        data = debug["data"]
        assert isinstance(data, dict)
        scopes = data["scopes"]
        assert isinstance(scopes, list)
        scopes.remove("pages_messaging")

    with pytest.raises(MetaTokenValidationError):
        validate_payloads(debug, profile, page, expected_app_id=app_id)
