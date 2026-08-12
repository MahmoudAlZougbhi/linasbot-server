"""Wave 1: disabled product modules are inaccessible for ALL tenants (including linas)."""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api_security import DashboardAuthMiddleware
from services.dashboard_session_service import SessionRecord
from services.product_features import (
    DISABLED_PRODUCT_MESSAGE,
    is_disabled_api_path,
)


def _session(*, tenant_id: str = "linas", role: str = "admin") -> SessionRecord:
    return SessionRecord(
        session_id="sess-wave1",
        user_id="user-wave1",
        email="admin@example.com",
        role=role,
        permissions=None,
        tenant_id=tenant_id,
        csrf_token="csrf",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )


def test_disabled_api_path_matcher() -> None:
    assert is_disabled_api_path("/api/live-chat/unified-chats") is False
    assert is_disabled_api_path("/api/flow/events") is False
    assert is_disabled_api_path("/api/chat-history/foo") is False
    assert is_disabled_api_path("/api/media/audio") is False
    assert is_disabled_api_path("/api/smart-messaging/campaigns") is True
    assert is_disabled_api_path("/api/test/foo") is True
    assert is_disabled_api_path("/api/test") is True
    assert is_disabled_api_path("/api/test-message") is True
    assert is_disabled_api_path("/api/test-image") is True
    assert is_disabled_api_path("/api/test-voice") is True
    assert is_disabled_api_path("/api/test-voice-text") is True
    assert is_disabled_api_path("/api/test-voice-upload") is True
    assert is_disabled_api_path("/api/test-image-upload") is True
    assert is_disabled_api_path("/api/switch-provider") is True
    assert is_disabled_api_path("/api/meta/social-posts/publish") is True
    assert is_disabled_api_path("/api/settings/clinic") is True
    assert is_disabled_api_path("/api/stats") is True
    assert (
        is_disabled_api_path("/api/content-files/knowledge/list") is False
    )  # 410 via handler, not product-disable prefix
    assert is_disabled_api_path("/api/instructions/get") is False
    assert is_disabled_api_path("/api/cm/draft") is False
    assert is_disabled_api_path("/api/meta/connections") is False
    assert is_disabled_api_path("/api/billing/wallet") is False
    assert is_disabled_api_path("/api/auth/me") is False


def _client_for(session: SessionRecord, monkeypatch) -> TestClient:
    from modules import api_security

    monkeypatch.setattr(api_security.session_service, "get_valid_session", lambda _cookie: session)
    app = FastAPI()
    app.add_middleware(DashboardAuthMiddleware)

    @app.get("/api/live-chat/unified-chats")
    async def live_chat() -> dict[str, bool]:
        return {"reached": True}

    @app.get("/api/smart-messaging/status")
    async def smart() -> dict[str, bool]:
        return {"reached": True}

    @app.get("/api/test/ping")
    async def testing() -> dict[str, bool]:
        return {"reached": True}

    @app.get("/api/flow/summary")
    async def flow() -> dict[str, bool]:
        return {"reached": True}

    @app.get("/api/cm/meta")
    async def cm_meta() -> dict[str, bool]:
        return {"reached": True}

    client = TestClient(app)
    client.cookies.set("linas_session", "opaque")
    return client


def test_disabled_modules_blocked_for_linas_admin(monkeypatch) -> None:
    client = _client_for(_session(tenant_id="linas"), monkeypatch)

    for path in (
        "/api/smart-messaging/status",
        "/api/test/ping",
    ):
        res = client.get(path)
        assert res.status_code == 403, path
        body = res.json()
        assert body["code"] == "PRODUCT_MODULE_DISABLED"
        assert body["error"] == DISABLED_PRODUCT_MESSAGE
        assert body.get("reached") is None

    # Live Chat + Interaction Logs are restored.
    for path in ("/api/live-chat/unified-chats", "/api/flow/summary"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert res.json() == {"reached": True}


def test_disabled_modules_blocked_for_saas_tenant(monkeypatch) -> None:
    client = _client_for(_session(tenant_id="acme-gym"), monkeypatch)

    res = client.get("/api/smart-messaging/status")
    assert res.status_code == 403
    assert res.json()["code"] == "PRODUCT_MODULE_DISABLED"

    live = client.get("/api/live-chat/unified-chats")
    # Live Chat is restored for Linas, but still fail-closed for other tenants
    # until the store has an explicit tenant-aware query path.
    assert live.status_code == 403
    assert live.json()["error"] == "Tenant-isolated API unavailable"

    # CM still allowed for SaaS (not a disabled module)
    allowed = client.get("/api/cm/meta")
    assert allowed.status_code == 200
    assert allowed.json() == {"reached": True}
