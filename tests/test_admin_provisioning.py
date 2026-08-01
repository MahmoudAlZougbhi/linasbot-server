"""Isolated tests for offline first-admin provisioning (no HTTP bootstrap)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.admin_provisioning_service import (
    ProvisionResult,
    audit_line,
    provision_first_admin,
    validate_provision_password,
)


def test_rejects_known_default_password() -> None:
    with pytest.raises(ValueError, match="known/default"):
        validate_provision_password("password12345")
    with pytest.raises(ValueError, match="known/default"):
        validate_provision_password("admin" + "123" + "!!!!")  # banned stem + padding
    with pytest.raises(ValueError, match="at least"):
        validate_provision_password("short")


def test_provision_refuses_when_users_exist() -> None:
    with patch("services.admin_provisioning_service.count_existing_users", return_value=1):
        result = provision_first_admin(
            email="owner@example.com",
            password="SecurePassPhrase99!",
            name="Owner",
        )
    assert result.status == "already_provisioned"
    assert result.user_id is None


def test_provision_creates_when_empty() -> None:
    created = {"id": "u-1", "email": "owner@example.com", "role": "admin"}
    with (
        patch("services.admin_provisioning_service.count_existing_users", return_value=0),
        patch("services.admin_provisioning_service.user_service.create_user", return_value=created) as create,
    ):
        result = provision_first_admin(
            email="Owner@Example.com",
            password="SecurePassPhrase99!",
            name="Owner",
        )
    assert result.status == "created"
    assert result.email == "owner@example.com"
    assert result.user_id == "u-1"
    create.assert_called_once()
    args, kwargs = create.call_args
    assert args[0]["role"] == "admin"
    assert args[0]["email"] == "owner@example.com"
    assert "password" in args[0]


def test_audit_line_never_includes_password() -> None:
    result = ProvisionResult(status="created", message="ok", email="a@b.com", user_id="1")
    line = audit_line(result)
    blob = str(line).lower()
    assert "password" not in blob
    assert line["email"] == "a@b.com"


def test_no_public_http_bootstrap_route() -> None:
    from modules.api_security import is_public_api

    assert not is_public_api("POST", "/api/auth/bootstrap-admin")
    # Route must not be mounted
    from fastapi.routing import APIRoute

    import modules.auth_api  # noqa: F401
    from modules.core import app

    paths = {(tuple(sorted(r.methods)), r.path) for r in app.routes if isinstance(r, APIRoute)}
    assert not any("/api/auth/bootstrap-admin" == path for _, path in paths)


def test_logout_not_public_requires_session_and_csrf() -> None:
    from modules.api_security import is_public_api

    assert not is_public_api("POST", "/api/auth/logout")
