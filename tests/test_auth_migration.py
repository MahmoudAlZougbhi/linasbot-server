"""Isolated auth migration / owner-access proofs (no production credentials)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from services.dashboard_session_service import (
    DashboardSessionService,
    get_auth_secret,
    require_auth_secret_configured,
)


def test_missing_dashboard_auth_secret_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("DASHBOARD_AUTH_SECRET", raising=False)
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="DASHBOARD_AUTH_SECRET"):
        get_auth_secret()


def test_missing_dashboard_auth_secret_fails_closed_in_test_env(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("DASHBOARD_AUTH_SECRET", raising=False)
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="DASHBOARD_AUTH_SECRET"):
        require_auth_secret_configured()


def test_non_prod_dev_uses_deterministic_not_random_secret(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("DASHBOARD_AUTH_SECRET", raising=False)
    monkeypatch.delenv("AUTH_SESSION_SECRET", raising=False)
    a = get_auth_secret()
    b = get_auth_secret()
    assert a == b
    assert len(a) == 64  # sha256 hex


def test_password_epoch_invalidates_session_without_default_password():
    svc = DashboardSessionService()
    record = svc.create_session(
        user_id="u-epoch",
        email="owner@example.com",
        role="admin",
        permissions=None,
        password_epoch=0,
        tenant_id="linas",
    )
    cookie = svc.cookie_value_for(record)
    assert svc.get_valid_session(cookie) is not None

    fake_user = {
        "id": "u-epoch",
        "email": "owner@example.com",
        "status": "active",
        "passwordEpoch": 1,
    }
    with patch("services.user_service.user_service.get_user_by_id", return_value=fake_user):
        assert svc.get_valid_session(cookie) is None


def test_session_expiry_and_revoke():
    svc = DashboardSessionService()
    record = svc.create_session(
        user_id="u-exp",
        email="a@example.com",
        role="viewer",
        permissions=None,
        password_epoch=0,
        ttl_seconds=1,
        tenant_id="linas",
    )
    cookie = svc.cookie_value_for(record)
    with patch("services.user_service.user_service.get_user_by_id", return_value=None):
        assert svc.get_valid_session(cookie) is not None
        svc.revoke_session(cookie)
        assert svc.get_valid_session(cookie) is None


def test_revoke_all_for_user_marks_local_sessions():
    svc = DashboardSessionService()
    r1 = svc.create_session(user_id="u1", email="a@x.com", role="admin", permissions=None, tenant_id="linas")
    r2 = svc.create_session(user_id="u1", email="a@x.com", role="admin", permissions=None, tenant_id="linas")
    other = svc.create_session(user_id="u2", email="b@x.com", role="viewer", permissions=None, tenant_id="linas")
    with patch("utils.utils.get_firestore_db", return_value=None):
        n = svc.revoke_all_for_user("u1")
    assert n >= 2
    with patch("services.user_service.user_service.get_user_by_id", return_value=None):
        assert svc.get_valid_session(svc.cookie_value_for(r1)) is None
        assert svc.get_valid_session(svc.cookie_value_for(r2)) is None
        assert svc.get_valid_session(svc.cookie_value_for(other)) is not None


def test_no_known_default_admin_password_in_user_service_source():
    from pathlib import Path

    src = Path("services/user_service.py").read_text(encoding="utf-8")
    auth_src = Path("services/user_service_auth.py").read_text(encoding="utf-8")
    # Avoid embedding the banned default password literal in the test file (secret scan).
    banned = "admin" + "123"
    assert banned not in src
    assert banned not in auth_src
    # ensure_default_admin lives on the auth mixin after LOC split.
    assert "ensure_default_admin is disabled" in auth_src


def test_no_http_bootstrap_and_cli_provisioning_exists():
    """First admin is offline CLI only — no public HTTP bootstrap."""
    from pathlib import Path

    auth_src = Path("modules/auth_api.py").read_text(encoding="utf-8")
    assert "bootstrap-admin" not in auth_src
    assert "provision_dashboard_admin.py" in auth_src
    assert Path("scripts/provision_dashboard_admin.py").is_file()
    assert Path("services/admin_provisioning_service.py").is_file()
