"""Dashboard user management must never cross tenant boundaries."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from modules import auth_api
from modules.api_security import DashboardAuthMiddleware
from services.dashboard_session_service import SessionRecord


def _request(tenant_id: str = "tenant-a") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/users",
            "query_string": b"",
            "headers": [],
        }
    )
    request.state.dashboard_session = SessionRecord(
        session_id="session-a",
        user_id="admin-a",
        email="admin@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
        csrf_token="csrf",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    return request


@pytest.mark.asyncio
async def test_user_list_is_filtered_to_session_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    users = [
        {"id": "a", "email": "a@example.com", "tenantId": "tenant-a"},
        {"id": "b", "email": "b@example.com", "tenantId": "tenant-b"},
    ]
    monkeypatch.setattr(auth_api.user_service, "get_all_users", lambda: users)

    response = await auth_api.get_users(_request())

    assert response == {"success": True, "users": [users[0]]}


@pytest.mark.asyncio
async def test_create_user_rejects_client_supplied_other_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def create_user(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(auth_api.user_service, "create_user", create_user)
    body = auth_api.CreateUserRequest(
        email="new@example.com",
        password="test-password-only",
        tenant_id="tenant-b",
    )

    with pytest.raises(HTTPException) as blocked:
        await auth_api.create_user(body, _request())

    assert blocked.value.status_code == 403
    assert called is False


@pytest.mark.asyncio
async def test_update_and_delete_hide_other_tenant_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_api.user_service,
        "get_user_by_id",
        lambda _user_id: {"id": "foreign", "tenantId": "tenant-b"},
    )

    with pytest.raises(HTTPException) as update_blocked:
        await auth_api.update_user("foreign", auth_api.UpdateUserRequest(name="No"), _request())
    with pytest.raises(HTTPException) as delete_blocked:
        await auth_api.delete_user("foreign", _request())

    assert update_blocked.value.status_code == 404
    assert delete_blocked.value.status_code == 404


def test_external_tenant_middleware_allows_only_auth_and_meta_control_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules import api_security

    external_session = _request().state.dashboard_session
    monkeypatch.setattr(api_security.session_service, "get_valid_session", lambda _cookie: external_session)
    app = FastAPI()
    app.add_middleware(DashboardAuthMiddleware)

    @app.get("/api/settings")
    async def settings() -> dict[str, bool]:
        return {"reached": True}

    @app.get("/api/meta/connections")
    async def meta_connections() -> dict[str, bool]:
        return {"reached": True}

    client = TestClient(app)
    client.cookies.set("linas_session", "opaque")

    denied = client.get("/api/settings")
    allowed = client.get("/api/meta/connections")

    assert denied.status_code == 403
    assert denied.json()["error"] == "Tenant-isolated API unavailable"
    assert allowed.status_code == 200
    assert allowed.json() == {"reached": True}
