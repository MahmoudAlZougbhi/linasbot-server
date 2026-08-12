"""Testing Lab Meta social HTTP surface is product-disabled (hyphenated routes)."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api_security import DashboardAuthMiddleware
from services.dashboard_session_service import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, SessionRecord
from services.product_features import is_disabled_api_path


def test_hyphenated_lab_paths_are_disabled() -> None:
    assert is_disabled_api_path("/api/test-message") is True
    assert is_disabled_api_path("/api/test-image") is True
    assert is_disabled_api_path("/api/test-voice") is True


def test_lab_test_message_blocked_by_middleware(monkeypatch) -> None:
    session = SessionRecord(
        session_id="sess-lab",
        user_id="lab-admin",
        email="lab-admin@example.com",
        role="admin",
        permissions={"testing": True},
        tenant_id="linas",
        csrf_token="csrf-lab",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    from modules import api_security

    monkeypatch.setattr(api_security.session_service, "get_valid_session", lambda _cookie: session)
    app = FastAPI()
    app.add_middleware(DashboardAuthMiddleware)

    @app.post("/api/test-message")
    async def lab() -> dict[str, bool]:
        return {"reached": True}

    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, "cookie")
    client.cookies.set(CSRF_COOKIE_NAME, session.csrf_token)
    client.headers[CSRF_HEADER_NAME] = session.csrf_token
    response = client.post("/api/test-message", json={"phone": "1", "message": "hi", "channel": "instagram"})
    assert response.status_code == 403, response.text
    assert response.json().get("reached") is None
