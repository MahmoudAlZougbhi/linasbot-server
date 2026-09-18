"""Owner Portal domain freeze: ownership, URLs, and platform_owner authorization."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from modules.api_security import require_platform_owner
from services.dashboard.dashboard_session_service import SESSION_COOKIE_NAME, session_service

ROOT = Path(__file__).resolve().parents[1]

GONE = (
    "dashboard/src/pages/owner",
    "services/owner_copilot/owner_portal_service.py",
)

KEEP = (
    "dashboard/src/owner_portal/OwnerPortalRoutes.jsx",
    "dashboard/src/owner_portal/api/ownerApi.js",
    "dashboard/src/owner_portal/components/OwnerPortalShell.jsx",
    "dashboard/src/owner_portal/components/OwnerActivationBanner.jsx",
    "dashboard/src/owner_portal/pages/OwnerOverview.jsx",
    "dashboard/src/owner_portal/pages/OwnerUsers.jsx",
    "dashboard/src/owner_portal/pages/OwnerMessages.jsx",
    "dashboard/src/owner_portal/pages/OwnerCatalog.jsx",
    "dashboard/src/owner_portal/pages/OwnerCosts.jsx",
    "services/owner_portal/overview.py",
    "services/owner_portal/users.py",
    "services/owner_portal/catalog.py",
    "services/owner_portal/costs.py",
    "services/owner_portal/messages.py",
    "services/owner_portal/activation.py",
    "services/owner_copilot/brain.py",
    "modules/platform_api.py",
    "modules/platform_message_api.py",
)

PLATFORM_GETS = (
    "/api/platform/analytics",
    "/api/platform/users",
    "/api/platform/message-catalog",
    "/api/platform/costs",
    "/api/platform/activation-readiness",
    "/api/platform/message-flows",
)


def test_owner_portal_paths_moved_and_copilot_stays_separate() -> None:
    missing = [rel for rel in KEEP if not (ROOT / rel).exists()]
    leftover = [rel for rel in GONE if (ROOT / rel).exists()]
    assert not missing, missing
    assert not leftover, leftover
    app = (ROOT / "dashboard/src/App.jsx").read_text(encoding="utf-8")
    routes = (ROOT / "dashboard/src/owner_portal/OwnerPortalRoutes.jsx").read_text(encoding="utf-8")
    assert "ownerPortalRouteElements" in app
    assert 'path="/owner"' in routes
    for slug in ("users", "messages", "catalog", "costs"):
        assert f'path="{slug}"' in routes
    assert "pages/owner" not in app
    copilot_init = (ROOT / "services/owner_copilot/__init__.py").read_text(encoding="utf-8")
    assert "owner_portal" not in copilot_init


def test_platform_http_facades_require_platform_owner() -> None:
    from inspect import getsource

    from modules import platform_api, platform_message_api, platform_search_api

    for fn in (
        platform_api.platform_analytics,
        platform_api.platform_users,
        platform_api.platform_update_user,
        platform_message_api.platform_message_catalog,
        platform_message_api.platform_costs,
        platform_message_api.platform_activation_readiness,
        platform_search_api.platform_force_reindex,
    ):
        src = getsource(fn)
        assert "require_platform_owner" in src
    assert callable(require_platform_owner)


def _client() -> TestClient:
    import modules.platform_api  # noqa: F401
    import modules.platform_message_api  # noqa: F401
    import modules.platform_search_api  # noqa: F401
    from modules.core import app

    return TestClient(app)


def _set_role(client: TestClient, *, role: str, user_id: str, tenant_id: str) -> None:
    rec = session_service.create_session(
        user_id=user_id,
        email=f"{user_id}@example.com",
        role=role,
        permissions=None,
        tenant_id=tenant_id,
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))


def test_anonymous_cannot_read_owner_portal_apis() -> None:
    client = _client()
    for path in PLATFORM_GETS:
        response = client.get(path)
        assert response.status_code == 401, (path, response.status_code, response.text)


def test_tenant_admin_and_owner_cannot_read_owner_portal_apis() -> None:
    client = _client()
    for role, user_id in (("admin", "tenant-admin"), ("owner", "tenant-owner")):
        _set_role(client, role=role, user_id=user_id, tenant_id="shop-a")
        for path in PLATFORM_GETS:
            response = client.get(path)
            assert response.status_code == 403, (role, path, response.status_code, response.text)


def test_platform_owner_can_read_owner_portal_apis(monkeypatch) -> None:
    monkeypatch.setattr("modules.platform_api.analytics", lambda _range: {"range": _range, "subscribers": 0})
    monkeypatch.setattr("modules.platform_api.list_subscribers", lambda: [])
    monkeypatch.setattr("modules.platform_message_api.get_message_catalog", lambda: {"plans": []})
    monkeypatch.setattr("modules.platform_message_api.load_platform_costs", lambda **_k: {"totals": {}})
    monkeypatch.setattr("modules.platform_message_api.activation_readiness", lambda: {"ready_to_enable": False})
    monkeypatch.setattr("modules.platform_message_api.list_platform_message_flows", lambda **_k: [])
    client = _client()
    _set_role(client, role="platform_owner", user_id="platform-1", tenant_id="linas")
    for path in PLATFORM_GETS:
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code, response.text)
        body = response.json()
        assert body.get("success") is True
