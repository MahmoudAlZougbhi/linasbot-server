"""Social-only accounts log in from Google/Apple instead of 409 link_required."""

from __future__ import annotations

from services.social_account_sign_in import is_social_only_account


def test_password_account_is_not_social_only() -> None:
    assert is_social_only_account({"id": "u1", "status": "active"}) is False
    assert is_social_only_account({"id": "u1", "status": "active", "passwordLoginEnabled": True}) is False


def test_google_or_apple_created_account_is_social_only() -> None:
    assert (
        is_social_only_account(
            {"id": "u1", "status": "active", "passwordLoginEnabled": False, "createdBy": "google-sign-in"}
        )
        is True
    )
    assert is_social_only_account({"id": "u1", "status": "active", "createdBy": "apple-sign-in"}) is True


def test_inactive_or_missing_user_is_not_social_only() -> None:
    assert is_social_only_account(None) is False
    assert is_social_only_account({"id": "u1", "status": "disabled", "passwordLoginEnabled": False}) is False
