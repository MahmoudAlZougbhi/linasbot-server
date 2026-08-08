"""Public SaaS landing, registration, and compliance route tests."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from modules.api_security import is_public_api


@pytest.fixture(scope="module")
def app_client() -> TestClient:
    import main  # noqa: F401
    from modules.core import app

    return TestClient(app)


def test_register_is_public_api() -> None:
    assert is_public_api("POST", "/api/auth/register")
    assert not is_public_api("POST", "/api/auth/logout")


def test_compliance_pages_remain_public(app_client: TestClient) -> None:
    for path in ("/privacy-policy", "/terms", "/data-deletion"):
        response = app_client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        body = response.text
        assert "Home" in body
        assert "/about" in body
        assert "/contact" in body


def test_meta_webhook_and_oauth_routes_still_registered() -> None:
    import main  # noqa: F401
    from modules.core import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/webhook" in paths
    assert "/webhook/meta-messaging" in paths
    assert "/oauth/meta/callback" in paths
    assert "/oauth/meta/deauthorize" in paths
    assert "/oauth/meta/data-deletion" in paths
    assert "/meta/deauthorize" in paths
    assert "/privacy-policy" in paths
    assert "/terms" in paths
    assert "/data-deletion" in paths
    assert "/api/auth/register" in paths


def test_nginx_proxies_oauth_and_deauthorize() -> None:
    conf = Path(__file__).resolve().parents[1] / "deploy" / "nginx-linasaibot.conf"
    text = conf.read_text(encoding="utf-8")
    assert "location ^~ /oauth/" in text
    assert "location = /meta/deauthorize" in text
    assert "location ^~ /data-deletion/status/" in text
    assert "location = /privacy-policy" in text
    assert "location ^~ /webhook" in text


def test_register_creates_isolated_tenant(app_client: TestClient) -> None:
    created = {
        "id": "user-saas-1",
        "email": "owner@example-biz.com",
        "name": "Example Biz",
        "role": "admin",
        "permissions": None,
        "tenantId": "example-biz",
        "businessName": "Example Biz",
        "status": "active",
        "passwordEpoch": 0,
    }

    with mock.patch("services.tenant_registration_service.register_company_account") as register_mock:
        from services.tenant_registration_service import RegistrationResult

        register_mock.return_value = RegistrationResult(
            user=created,
            tenant_id="example-biz",
            business_name="Example Biz",
        )
        response = app_client.post(
            "/api/auth/register",
            json={
                "business_name": "Example Biz",
                "email": "owner@example-biz.com",
                "password": "SecurePassphrase99!",
                "name": "Owner",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["tenant_id"] == "example-biz"
    assert payload["tenant_id"] != "linas"
    assert payload["user"]["email"] == "owner@example-biz.com"
    assert "linas_session" in response.cookies


def test_register_rejects_weak_password(app_client: TestClient) -> None:
    response = app_client.post(
        "/api/auth/register",
        json={
            "business_name": "Weak Co",
            "email": "weak@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is False
    assert (
        "password" in str(payload.get("error") or "").lower()
        or "known" in str(payload.get("error") or "").lower()
        or "default" in str(payload.get("error") or "").lower()
    )


def test_allocate_tenant_never_returns_reserved_linas() -> None:
    from services.tenant_registration_service import allocate_tenant_id

    with mock.patch("services.tenant_registration_service.user_service") as users:
        users._normalize_tenant_id.side_effect = lambda value: str(value).strip().lower()
        users.tenant_id_exists.return_value = False
        tenant_id = allocate_tenant_id("Linas")
        assert tenant_id != "linas"
        assert tenant_id.startswith("biz-")
