"""Owner-only deletion of a saved copilot Q&A."""

from __future__ import annotations

from fastapi.testclient import TestClient

from services.dashboard.dashboard_session_service import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    session_service,
)


def _client() -> TestClient:
    import modules.platform_copilot_portal_api  # noqa: F401
    from modules.core import app

    return TestClient(app)


def _session(client: TestClient, role: str) -> None:
    rec = session_service.create_session(
        user_id="user-1",
        email="user@example.com",
        role=role,
        permissions=None,
        tenant_id="platform" if role == "platform_owner" else "linas",
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)


def test_delete_qa_requires_owner_and_csrf(monkeypatch) -> None:
    client = _client()
    assert client.delete("/api/platform/copilot/qa/missing").status_code == 401
    _session(client, "admin")
    client.headers[CSRF_HEADER_NAME] = client.cookies.get(CSRF_COOKIE_NAME) or ""
    assert client.delete("/api/platform/copilot/qa/missing").status_code == 403

    owner = _client()
    _session(owner, "platform_owner")
    assert owner.delete("/api/platform/copilot/qa/missing").status_code == 403
    owner.headers[CSRF_HEADER_NAME] = owner.cookies.get(CSRF_COOKIE_NAME) or ""
    monkeypatch.setattr("services.owner_portal.owner_qa.delete_qa", lambda _qa_id: False)
    assert owner.delete("/api/platform/copilot/qa/missing").status_code == 404
    monkeypatch.setattr("services.owner_portal.owner_qa.delete_qa", lambda _qa_id: True)
    monkeypatch.setattr("services.team.platform_owner_service.platform_owner_service.log_action", lambda **_k: None)
    assert owner.delete("/api/platform/copilot/qa/qa-1").status_code == 200
