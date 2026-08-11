"""LOC split: user_service auth mixin under 500 lines; public exports preserved."""

from __future__ import annotations

from pathlib import Path

from services.user_service import AuthBackendUnavailableError, UserService, user_service
from services.user_service_auth import UserServiceAuthMixin


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_user_service_modules_under_500_lines() -> None:
    assert _line_count("services/user_service.py") < 500
    assert _line_count("services/user_service_auth.py") < 500


def test_user_service_preserves_public_api_via_mixin() -> None:
    assert issubclass(UserService, UserServiceAuthMixin)
    assert isinstance(user_service, UserService)
    assert issubclass(AuthBackendUnavailableError, RuntimeError)
    for name in (
        "authenticate",
        "create_user",
        "get_user_by_email",
        "change_password",
        "_sanitize_user",
        "_hash_password",
    ):
        assert callable(getattr(user_service, name))
