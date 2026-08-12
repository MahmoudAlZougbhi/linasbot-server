"""GET /api/live-chat/status requires elevated role (admin / platform_owner)."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from services.dashboard_session_service import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, session_service

_ROUTE_MODULES = (
    "modules.live_chat_api",
    "modules.live_chat_api_debug",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
    os.environ.setdefault("LINASLASER_API_TOKEN", "test-token")
    os.environ.setdefault("DASHBOARD_AUTH_SECRET", "live-chat-status-test-secret")
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("DISABLE_API_DOCS", "true")

    for mod in _ROUTE_MODULES:
        __import__(mod)

    from modules.core import app

    return TestClient(app)


def _clear_client_auth(client: TestClient) -> None:
    client.cookies.clear()


def _set_role_session(client: TestClient, *, role: str, user_id: str = "status-test-user") -> None:
    rec = session_service.create_session(
        user_id=user_id,
        email=f"{user_id}@example.com",
        role=role,
        permissions=None,
        tenant_id="linas",
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)


def test_live_chat_status_unauthenticated_401(client: TestClient) -> None:
    _clear_client_auth(client)
    response = client.get("/api/live-chat/status")
    assert response.status_code == 401


def test_live_chat_status_forbidden_for_operator(client: TestClient) -> None:
    _clear_client_auth(client)
    _set_role_session(client, role="operator", user_id="status-operator")
    response = client.get("/api/live-chat/status")
    assert response.status_code == 403
    assert "Elevated role required" in (response.json().get("detail") or "")


def test_live_chat_status_allowed_for_admin(client: TestClient) -> None:
    _clear_client_auth(client)
    _set_role_session(client, role="admin", user_id="status-admin")
    response = client.get("/api/live-chat/status")
    # Elevation passes; Firestore may be unavailable in unit tests.
    assert response.status_code == 200
    body = response.json()
    assert "index_count" in body or body.get("success") is False
