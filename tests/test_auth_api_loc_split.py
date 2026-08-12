"""LOC split: auth_api re-exports common models/users under 500 lines."""

from __future__ import annotations

from pathlib import Path

from modules.auth_api_common import (
    AUTH_LOGIN_TIMEOUT_SECONDS,
    CreateUserRequest,
    LoginRequest,
    _cookie_samesite,
)


def _line_count(rel: str) -> int:
    return len(Path(rel).read_text(encoding="utf-8").splitlines())


def test_auth_api_modules_under_500_lines() -> None:
    assert _line_count("modules/auth_api.py") < 500
    assert _line_count("modules/auth_api_common.py") < 500
    assert _line_count("modules/auth_users_api.py") < 500


def test_auth_api_preserves_public_imports_and_provisioning_contract() -> None:
    from modules import auth_api

    assert auth_api.CreateUserRequest is CreateUserRequest
    assert auth_api.LoginRequest is LoginRequest
    assert callable(auth_api.get_users)
    assert callable(auth_api.create_user)
    assert callable(auth_api.update_user)
    assert callable(auth_api.delete_user)
    assert AUTH_LOGIN_TIMEOUT_SECONDS > 0
    assert _cookie_samesite() in {"lax", "strict", "none"}

    auth_src = Path("modules/auth_api.py").read_text(encoding="utf-8")
    assert "bootstrap-admin" not in auth_src
    assert "provision_dashboard_admin.py" in auth_src
