"""Endpoint auth matrix: enumerate /api routes, classify public vs protected, enforce deny-by-default."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from modules.api_security import (
    _PUBLIC_EXACT,
    _PUBLIC_PREFIX,
    is_public_api,
)
from services.dashboard_session_service import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, session_service

# Populated by test_route_inventory_counts for reporting (no response bodies / PII).
ENDPOINT_AUTH_COUNTS: dict[str, int] = {}

_ROUTE_MODULES = (
    "modules.analytics_api",
    "modules.auth_api",
    "modules.mobile_auth_api",
    "modules.owner_ai_api",
    "modules.entitlements_api",
    "modules.creative_api",
    "modules.schedule_api",
    "modules.platform_api",
    "modules.mobile_integrations_api",
    "modules.mobile_stt_api",
    "modules.store_iap_api",
    "modules.queue_api",
    "modules.dashboard_api",
    "modules.live_chat_api",
    "modules.media_api",
    "modules.settings_api",
    "modules.smart_messaging_api",
    "modules.local_qa_api",
    "modules.content_files_api",
    "modules.qa_api",
    "modules.feedback_api",
    "modules.instructions_api",
    "modules.flow_api",
    "modules.training_files_api",
    "modules.chat_history_api",
    "modules.webhook_handlers",
    "modules.meta_connections_api",
    "modules.meta_messaging_webhook",
    "modules.meta_social_posts_api",
    "modules.wallet_api",
)

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})

_PARAM_DEFAULTS: dict[str, str] = {
    "qa_id": "qa-matrix-test",
    "user_id": "9613000000",
    "conversation_id": "conv-matrix-test",
    "file_id": "style_guide",
    "section": "knowledge",
    "template_id": "1",
    "category": "general",
    "message_id": "msg-matrix-test",
    "service_id": "svc-matrix-test",
    "post_id": "post-matrix-test",
    "tenant_id": "tenant-matrix-test",
}


def _fill_path_params(path: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        name = match.group(1)
        return _PARAM_DEFAULTS.get(name, f"test-{name}")

    return re.sub(r"\{([^}]+)\}", _replace, path)


def _enumerate_api_routes(app: Any) -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods):
            if method in _HTTP_METHODS and route.path.startswith("/api/"):
                routes.append((method, route.path))
    return sorted(set(routes))


def _classify_routes(routes: list[tuple[str, str]]) -> dict[str, Any]:
    public: list[tuple[str, str]] = []
    protected: list[tuple[str, str]] = []
    for method, path in routes:
        if is_public_api(method, path):
            public.append((method, path))
        else:
            protected.append((method, path))
    protected_gets = [(m, p) for m, p in protected if m == "GET"]
    protected_mutations = [(m, p) for m, p in protected if m in _MUTATION_METHODS]
    return {
        "all": routes,
        "public": public,
        "protected": protected,
        "protected_gets": protected_gets,
        "protected_mutations": protected_mutations,
        "counts": {
            "total_api_routes": len(routes),
            "public": len(public),
            "protected": len(protected),
            "protected_gets": len(protected_gets),
            "protected_mutations": len(protected_mutations),
        },
    }


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ["LINASLASER_API_BASE_URL"] = "https://example.com"
    os.environ["LINASLASER_API_TOKEN"] = "test-token"
    os.environ["DASHBOARD_AUTH_SECRET"] = "matrix-test-secret"
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DISABLE_API_DOCS"] = "true"
    os.environ.pop("ALLOW_DEBUG_SIMULATE_WEBHOOK", None)

    for mod in _ROUTE_MODULES:
        __import__(mod)

    from modules.core import app

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_matrix(client: TestClient) -> dict[str, Any]:
    routes = _enumerate_api_routes(client.app)
    return _classify_routes(routes)


def _clear_client_auth(client: TestClient) -> None:
    client.cookies.clear()


def _set_admin_session(client: TestClient, *, with_csrf_header: bool = False) -> str:
    rec = session_service.create_session(
        user_id="matrix-admin",
        email="matrix-admin@example.com",
        role="admin",
        permissions=None,
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
    if with_csrf_header:
        client.headers[CSRF_HEADER_NAME] = rec.csrf_token
    else:
        client.headers.pop(CSRF_HEADER_NAME, None)
    return rec.csrf_token


class TestRouteInventory:
    def test_route_inventory_counts(self, auth_matrix: dict[str, Any]) -> None:
        counts = auth_matrix["counts"]
        ENDPOINT_AUTH_COUNTS.clear()
        ENDPOINT_AUTH_COUNTS.update(counts)

        assert counts["total_api_routes"] >= 100
        assert counts["public"] == len(_PUBLIC_EXACT)
        assert counts["protected"] == counts["total_api_routes"] - counts["public"]
        assert counts["protected_gets"] + counts["protected_mutations"] <= counts["protected"]

        # Exact inventory after removing public bootstrap-admin; logout is session+CSRF protected.
        # +forgot/reset/verify/resend auth + billing packages/webhook (wallet APIs).
        # +meta reconnect endpoint for first-party bindings.
        assert counts["total_api_routes"] == 196
        assert counts["public"] == 15
        assert counts["protected"] == 181
        public_set = set(auth_matrix["public"])
        assert public_set == {
            ("GET", "/api/health"),
            ("GET", "/api/ready"),
            ("GET", "/api/queue/ready"),
            ("POST", "/api/auth/login"),
            ("POST", "/api/auth/register"),
            ("POST", "/api/auth/forgot-password"),
            ("POST", "/api/auth/reset-password"),
            ("POST", "/api/auth/verify-email"),
            ("POST", "/api/auth/resend-verification"),
            ("GET", "/api/billing/packages"),
            ("POST", "/api/billing/stripe/webhook"),
            ("POST", "/api/auth/mobile/login"),
            ("POST", "/api/auth/mobile/refresh"),
            ("POST", "/api/entitlements/apple/notifications"),
            ("POST", "/api/entitlements/google/notifications"),
        }
        assert ("POST", "/api/auth/logout") not in public_set
        assert ("POST", "/api/auth/bootstrap-admin") not in public_set
        assert ("GET", "/api/billing/wallet") not in public_set
        assert ("GET", "/api/billing/wallet/analytics") not in public_set
        assert ("GET", "/api/settings/ai-limits") not in public_set
        assert ("POST", "/api/settings/ai-limits") not in public_set

    def test_public_allowlist_matches_api_security(self, auth_matrix: dict[str, Any]) -> None:
        discovered_public = set(auth_matrix["public"])
        for method, path in _PUBLIC_EXACT:
            assert (method, path) in discovered_public, f"missing public route {method} {path}"
        for method, path in discovered_public:
            assert is_public_api(method, path), f"unexpected public classification {method} {path}"
        for prefix in _PUBLIC_PREFIX:
            assert any(p.startswith(prefix) for _, p in discovered_public) or prefix == "", prefix


class TestProtectedGetMatrix:
    def test_protected_gets_return_401_without_session(self, client: TestClient, auth_matrix: dict[str, Any]) -> None:
        failures: list[str] = []
        for method, path in auth_matrix["protected_gets"]:
            _clear_client_auth(client)
            url = _fill_path_params(path)
            response = client.request(method, url)
            if response.status_code != 401:
                failures.append(f"{method} {url} -> {response.status_code}")
        assert not failures, "Protected GET auth failures:\n" + "\n".join(failures)


class TestProtectedMutationMatrix:
    def test_protected_mutations_return_401_without_session(
        self, client: TestClient, auth_matrix: dict[str, Any]
    ) -> None:
        failures: list[str] = []
        for method, path in auth_matrix["protected_mutations"]:
            _clear_client_auth(client)
            url = _fill_path_params(path)
            response = client.request(method, url, json={})
            if response.status_code != 401:
                failures.append(f"{method} {url} -> {response.status_code}")
        assert not failures, "Protected mutation auth failures:\n" + "\n".join(failures)

    def test_protected_mutations_require_csrf_when_authenticated(
        self, client: TestClient, auth_matrix: dict[str, Any]
    ) -> None:
        failures: list[str] = []
        for method, path in auth_matrix["protected_mutations"]:
            _clear_client_auth(client)
            _set_admin_session(client, with_csrf_header=False)
            url = _fill_path_params(path)
            response = client.request(method, url, json={})
            if response.status_code != 403:
                failures.append(f"{method} {url} -> {response.status_code}")
        assert not failures, "CSRF enforcement failures:\n" + "\n".join(failures)


class TestPublicEndpoints:
    def test_public_routes_not_401_without_session(self, client: TestClient, auth_matrix: dict[str, Any]) -> None:
        for method, path in auth_matrix["public"]:
            _clear_client_auth(client)
            url = _fill_path_params(path)
            if method in _MUTATION_METHODS:
                response = client.request(method, url, json={})
            else:
                response = client.request(method, url)
            assert response.status_code != 401, f"{method} {url} should remain public"


class TestDebugAndSimulationEndpoints:
    def test_docs_disabled_in_test_env(self, client: TestClient) -> None:
        for doc_path in ("/docs", "/redoc", "/openapi.json"):
            response = client.get(doc_path)
            assert response.status_code in {404, 401, 403}, doc_path

    def test_simulate_webhook_not_public(self, client: TestClient) -> None:
        _clear_client_auth(client)
        response = client.post(
            "/api/debug/simulate-webhook",
            json={"phone": "9613000000", "text": "hi"},
        )
        assert response.status_code == 401

    def test_simulate_webhook_disabled_when_authenticated_in_test(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ALLOW_DEBUG_SIMULATE_WEBHOOK", raising=False)
        _clear_client_auth(client)
        csrf = _set_admin_session(client, with_csrf_header=True)
        response = client.post(
            "/api/debug/simulate-webhook",
            json={"phone": "9613000000", "text": "hi"},
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert response.status_code == 403
        body = response.json()
        assert body.get("code") == "PRODUCT_MODULE_DISABLED"

    def test_simulate_webhook_disabled_in_production_like_env(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("ALLOW_DEBUG_SIMULATE_WEBHOOK", "true")
        _clear_client_auth(client)
        csrf = _set_admin_session(client, with_csrf_header=True)
        response = client.post(
            "/api/debug/simulate-webhook",
            json={"phone": "9613000000", "text": "hi"},
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert response.status_code == 403
        body = response.json()
        assert body.get("code") == "PRODUCT_MODULE_DISABLED"

    def test_debug_webhook_status_requires_auth(self, client: TestClient) -> None:
        _clear_client_auth(client)
        response = client.get("/api/debug/webhook-status")
        assert response.status_code == 401


class TestSocialLiveChatMutations:
    def _social_payload(self, path: str) -> dict[str, str]:
        base = {
            "conversation_id": "c-matrix",
            "user_id": "instagram:12345",
            "operator_id": "ignored",
        }
        if path.endswith("/send-message"):
            base["message"] = "hello"
        return base

    @pytest.mark.parametrize(
        "path",
        [
            "/api/live-chat/takeover",
            "/api/live-chat/send-message",
            "/api/live-chat/end-conversation",
        ],
    )
    def test_social_operator_mutations_forbidden(
        self, client: TestClient, path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ENVIRONMENT", "test")
        _clear_client_auth(client)
        csrf = _set_admin_session(client, with_csrf_header=True)
        response = client.post(
            path,
            json=self._social_payload(path),
            headers={CSRF_HEADER_NAME: csrf},
        )
        assert response.status_code == 403


class TestSSRFAndPathTraversal:
    def test_media_audio_unauthenticated_401(self, client: TestClient) -> None:
        _clear_client_auth(client)
        response = client.get("/api/media/audio", params={"url": "http://127.0.0.1:9/"})
        assert response.status_code == 401

    def test_media_audio_ssrf_blocked_when_authenticated(self, client: TestClient) -> None:
        _clear_client_auth(client)
        csrf = _set_admin_session(client, with_csrf_header=True)
        response = client.get(
            "/api/media/audio",
            params={"url": "http://127.0.0.1:9/"},
            headers={CSRF_HEADER_NAME: csrf},
        )
        # Live Chat media is enabled; SSRF guard must still reject loopback.
        assert response.status_code == 400

    def test_training_backup_path_traversal_blocked(self, tmp_path: Path) -> None:
        from services.safe_path import resolve_backup_filename

        root = tmp_path / "content"
        root.mkdir()
        (root / "style_guide_backup_1.txt").write_text("x")
        with pytest.raises(ValueError):
            resolve_backup_filename(
                root,
                "../style_guide_backup_1.txt",
                required_prefix="style_guide_backup_",
            )
