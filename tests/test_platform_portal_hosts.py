"""Platform owner portal hosts: CORS, login gate, email allowlist."""

from __future__ import annotations

from pathlib import Path

from services.platform_portal_hosts import (
    PLATFORM_OWNER_TENANT_ID,
    cors_public_origins,
    hostname_from_header,
    is_platform_portal_host,
    portal_login_error,
)


def test_portal_hosts_and_hostname_parsing() -> None:
    assert is_platform_portal_host("www.portal.linasaibot.com")
    assert is_platform_portal_host("portal.linasaibot.com:443")
    assert not is_platform_portal_host("www.linasaibot.com")
    assert hostname_from_header("www.portal.linasaibot.com:443") == "www.portal.linasaibot.com"


def test_portal_login_rejects_workspace_roles() -> None:
    host = "www.portal.linasaibot.com"
    assert portal_login_error(host, "admin")
    assert portal_login_error(host, "operator")
    assert portal_login_error("www.linasaibot.com", "admin") is None
    assert portal_login_error(host, "platform_owner") is None


def test_cookie_login_rejects_marketing_host() -> None:
    from services.platform_portal_hosts import cookie_login_error

    assert cookie_login_error("www.linasaibot.com", "admin")
    assert cookie_login_error("www.linasaibot.com", "platform_owner")
    assert cookie_login_error("localhost", "admin") is None
    assert cookie_login_error("www.portal.linasaibot.com", "platform_owner") is None
    assert cookie_login_error("www.portal.linasaibot.com", "admin")


def test_cors_includes_portal_https() -> None:
    prod = cors_public_origins(production=True)
    assert "https://www.portal.linasaibot.com" in prod
    assert "https://portal.linasaibot.com" in prod
    assert "http://www.portal.linasaibot.com" not in prod
    dev = cors_public_origins(production=False)
    assert "http://portal.linasaibot.com" in dev


def test_nginx_lists_portal_server_names() -> None:
    conf = Path(__file__).resolve().parents[1] / "deploy" / "nginx-linasaibot.conf"
    text = conf.read_text(encoding="utf-8")
    assert text.count("portal.linasaibot.com") >= 2
    assert text.count("www.portal.linasaibot.com") >= 2
    assert PLATFORM_OWNER_TENANT_ID == "platform"


def test_portal_login_http_rejects_workspace_admin() -> None:
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    import main  # noqa: F401
    from modules.core import app

    user = {
        "id": "u1",
        "email": "admin@linas.ai",
        "role": "admin",
        "tenantId": "linas",
        "status": "active",
        "passwordEpoch": 0,
    }
    with patch("modules.auth_api.user_service.authenticate", return_value=user):
        response = TestClient(app).post(
            "/api/auth/login",
            json={"email": "admin@linas.ai", "password": "SecurePassPhrase99!"},
            headers={"host": "www.portal.linasaibot.com"},
        )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is False
    assert "platform owner" in str(payload.get("error") or "").lower()
    assert "linas_session" not in response.cookies


def test_marketing_login_http_rejects_all_roles() -> None:
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    import main  # noqa: F401
    from modules.core import app

    user = {
        "id": "u1",
        "email": "owner@linasaibot.com",
        "role": "platform_owner",
        "tenantId": "platform",
        "status": "active",
        "passwordEpoch": 0,
    }
    with patch("modules.auth_api.user_service.authenticate", return_value=user):
        response = TestClient(app).post(
            "/api/auth/login",
            json={"email": "owner@linasaibot.com", "password": "SecurePassPhrase99!"},
            headers={"host": "www.linasaibot.com"},
        )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success"] is False
    assert "mobile app" in str(payload.get("error") or "").lower()
    assert "linas_session" not in response.cookies
