"""Wave 1 security regression tests (AuthN/AuthZ, SSRF, path traversal, secrets)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from modules.api_security import (
    _client_ip,
    auth_rate_limit_rules,
    is_public_api,
    is_social_user_id,
    required_permission_for,
    resolve_permissions,
)
from services.dashboard_session_service import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, session_service
from services.product_features import is_disabled_api_path
from services.safe_path import is_safe_relative_name, resolve_backup_filename, resolve_under_root
from services.ssrf_guard import SSRFValidationError, validate_fetch_url


class TestSafePath:
    def test_rejects_traversal_names(self):
        assert not is_safe_relative_name("../etc/passwd")
        assert not is_safe_relative_name("..\\windows")
        assert not is_safe_relative_name("/etc/passwd")
        assert not is_safe_relative_name("a/b")
        assert not is_safe_relative_name("x\x00y")
        assert is_safe_relative_name("style_guide_backup_20260101.txt")

    def test_resolve_under_root_blocks_escape(self, tmp_path):
        root = tmp_path / "content"
        root.mkdir()
        with pytest.raises(ValueError):
            resolve_under_root(root, "..", "secrets.txt")
        ok = resolve_under_root(root, "ok.txt")
        assert str(ok).startswith(str(root.resolve()))

    def test_backup_filename_prefix(self, tmp_path):
        root = tmp_path / "content"
        root.mkdir()
        (root / "style_guide_backup_1.txt").write_text("x")
        path = resolve_backup_filename(root, "style_guide_backup_1.txt", required_prefix="style_guide_backup_")
        assert path.exists()
        with pytest.raises(ValueError):
            resolve_backup_filename(root, "../style_guide_backup_1.txt", required_prefix="style_guide_backup_")
        with pytest.raises(ValueError):
            resolve_backup_filename(root, "other_backup_1.txt", required_prefix="style_guide_backup_")


class TestSSRFGuard:
    def test_blocks_http_and_loopback(self):
        with pytest.raises(SSRFValidationError):
            validate_fetch_url("http://127.0.0.1/x")
        with pytest.raises(SSRFValidationError):
            validate_fetch_url("https://127.0.0.1/x")
        with pytest.raises(SSRFValidationError):
            validate_fetch_url("https://169.254.169.254/latest/meta-data")
        with pytest.raises(SSRFValidationError):
            validate_fetch_url("https://192.168.1.1/a")

    def test_blocks_non_allowlisted_host(self):
        with pytest.raises(SSRFValidationError):
            validate_fetch_url("https://evil.example/audio.ogg")

    def test_allows_firebase_host_without_dns_if_mocked(self):
        with patch("services.ssrf_guard.socket.getaddrinfo") as gai:
            gai.return_value = [(0, 0, 0, 0, ("1.2.3.4", 0))]
            url = validate_fetch_url("https://firebasestorage.googleapis.com/v0/b/x/o/a")
            assert url.startswith("https://firebasestorage.googleapis.com/")

    def test_dns_to_private_blocked(self):
        with patch("services.ssrf_guard.socket.getaddrinfo") as gai:
            gai.return_value = [(0, 0, 0, 0, ("10.0.0.5", 0))]
            with pytest.raises(SSRFValidationError):
                validate_fetch_url("https://firebasestorage.googleapis.com/v0/b/x")


class TestSessionService:
    def test_roundtrip_and_revoke(self):
        rec = session_service.create_session(
            user_id="u1",
            email="a@example.com",
            role="admin",
            permissions=None,
        )
        cookie = session_service.cookie_value_for(rec)
        loaded = session_service.get_valid_session(cookie)
        assert loaded is not None
        assert loaded.user_id == "u1"
        assert loaded.csrf_token
        session_service.revoke_session(cookie)
        assert session_service.get_valid_session(cookie) is None

    def test_tampered_cookie_rejected(self):
        rec = session_service.create_session(user_id="u2", email="b@example.com", role="viewer", permissions=None)
        cookie = session_service.cookie_value_for(rec) + "x"
        assert session_service.get_valid_session(cookie) is None


class TestRBACHelpers:
    def test_public_and_permissions(self):
        assert is_public_api("GET", "/api/health")
        assert is_public_api("POST", "/api/auth/login")
        assert is_public_api("POST", "/api/auth/register")
        assert not is_public_api("POST", "/api/auth/logout")
        assert not is_public_api("POST", "/api/auth/bootstrap-admin")
        assert not is_public_api("GET", "/api/analytics/summary")
        assert required_permission_for("GET", "/api/analytics/summary") == "analytics"
        assert required_permission_for("POST", "/api/smart-messaging/toggle") == "smartMessaging"
        assert required_permission_for("GET", "/api/content-files/knowledge/list") == "contentManagers"
        assert resolve_permissions("admin", None)["userManagement"] is True
        assert resolve_permissions("viewer", None)["userManagement"] is False
        assert is_social_user_id("instagram:123")
        assert is_social_user_id("facebook:123")
        assert not is_social_user_id("+96170000000")


class TestMontySecretNotTracked:
    def test_tracked_config_has_empty_api_key(self):
        root = Path(__file__).resolve().parents[1]
        data = json.loads((root / "config" / "montymobile_templates.json").read_text())
        key = (data.get("api_config") or {}).get("api_key") or ""
        assert key == ""
        assert (data.get("api_config") or {}).get("api_key_env") == "MONTYMOBILE_API_KEY"


class TestClientIpTrustedProxy:
    def _request(self, headers: dict[str, str], client_host: str = "10.0.0.9"):
        from starlette.requests import Request

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in headers.items()],
            "client": (client_host, 12345),
            "server": ("testserver", 80),
        }
        return Request(scope)

    def test_prefers_x_real_ip_over_spoofed_xff(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_MODE", raising=False)
        req = self._request(
            {
                "x-forwarded-for": "1.2.3.4, 10.0.0.9",
                "x-real-ip": "203.0.113.50",
            }
        )
        assert _client_ip(req) == "203.0.113.50"

    def test_ignores_xff_when_no_x_real_ip(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_MODE", raising=False)
        req = self._request({"x-forwarded-for": "1.2.3.4"})
        assert _client_ip(req) == "10.0.0.9"

    def test_direct_mode_ignores_forwarded_headers(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_MODE", "direct")
        req = self._request({"x-real-ip": "203.0.113.50", "x-forwarded-for": "1.2.3.4"})
        assert _client_ip(req) == "10.0.0.9"


class TestAuthRateLimitRules:
    def test_mobile_login_and_refresh_have_ip_and_identifier_buckets(self):
        login_rules = auth_rate_limit_rules("/api/auth/mobile/login", "9.9.9.9", "user@example.com")
        refresh_rules = auth_rate_limit_rules(
            "/api/auth/mobile/refresh", "9.9.9.9", "abcd1234fingerprint"
        )
        login_keys = {k for k, _, _ in login_rules}
        refresh_keys = {k for k, _, _ in refresh_rules}
        assert "mobile-login:9.9.9.9" in login_keys
        assert "mobile-login:id:user@example.com" in login_keys
        assert "mobile-refresh:9.9.9.9" in refresh_keys
        assert "mobile-refresh:id:abcd1234fingerprint" in refresh_keys

        # Match or stricter than dashboard login IP budget (10/300).
        dash = {k: (lim, win) for k, lim, win in auth_rate_limit_rules("/api/auth/login", "9.9.9.9", "user@example.com")}
        mobile = {k: (lim, win) for k, lim, win in login_rules}
        assert mobile["mobile-login:9.9.9.9"][0] <= dash["login:9.9.9.9"][0]
        assert mobile["mobile-login:id:user@example.com"][0] <= dash["login:id:user@example.com"][0]

    def test_password_reset_verify_resend_have_identifier_buckets(self):
        forgot = auth_rate_limit_rules("/api/auth/forgot-password", "1.1.1.1", "a@b.co")
        reset = auth_rate_limit_rules("/api/auth/reset-password", "1.1.1.1", "tokfingerprint")
        verify = auth_rate_limit_rules("/api/auth/verify-email", "1.1.1.1", "tokfingerprint")
        resend = auth_rate_limit_rules("/api/auth/resend-verification", "1.1.1.1", "a@b.co")
        assert any(k.startswith("forgot:id:") for k, _, _ in forgot)
        assert any(k.startswith("reset:id:") for k, _, _ in reset)
        assert any(k.startswith("verify:id:") for k, _, _ in verify)
        assert any(k.startswith("resend-verify:id:") for k, _, _ in resend)

    def test_disabled_product_paths_still_matched(self):
        # Regression: disabled-path gate remains in place (covered elsewhere; keep a smoke assert).
        assert is_disabled_api_path("/api/test/foo") is True
        assert is_disabled_api_path("/api/switch-provider") is True
        assert is_disabled_api_path("/api/auth/mobile/login") is False


@pytest.fixture(scope="module")
def client():
    os.environ["LINASLASER_API_BASE_URL"] = "https://example.com"
    os.environ["LINASLASER_API_TOKEN"] = "test-token"
    os.environ["DASHBOARD_AUTH_SECRET"] = "wave1-test-secret"
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DISABLE_API_DOCS"] = "true"
    from fastapi.testclient import TestClient

    # Import route modules
    import modules.analytics_api  # noqa: F401
    import modules.auth_api  # noqa: F401
    import modules.dashboard_api  # noqa: F401
    import modules.live_chat_api  # noqa: F401
    import modules.media_api  # noqa: F401
    import modules.settings_api  # noqa: F401
    import modules.smart_messaging_api  # noqa: F401
    from modules.core import app

    return TestClient(app)


class TestAPIAuthEnforcement:
    def test_protected_get_without_cookie_401(self, client):
        for path in [
            "/api/analytics/summary",
            "/api/auth/users",
            "/api/settings",
            "/api/smart-messaging/counts",
            "/api/live-chat/metrics",
            "/api/flow/logs",
            "/api/debug/webhook-status",
        ]:
            r = client.get(path)
            assert r.status_code == 401, path

    def test_health_public(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200

    def test_docs_disabled_when_flag_set(self, client):
        r = client.get("/docs")
        assert r.status_code in {404, 401, 403}

    def test_ssrf_endpoint_requires_auth_then_blocks(self, client):
        r = client.get("/api/media/audio", params={"url": "http://127.0.0.1:9/"})
        assert r.status_code == 401
        # Authenticated viewer with liveChat
        rec = session_service.create_session(user_id="op1", email="op@example.com", role="operator", permissions=None)
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
        r2 = client.get("/api/media/audio", params={"url": "http://127.0.0.1:9/"})
        # Live Chat media is enabled; SSRF guard must still reject loopback.
        assert r2.status_code == 400

    def test_simulate_webhook_disabled(self, client):
        rec = session_service.create_session(user_id="t1", email="t@example.com", role="admin", permissions=None)
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
        r = client.post(
            "/api/debug/simulate-webhook",
            json={"phone": "9613000000", "text": "hi"},
            headers={"X-CSRF-Token": rec.csrf_token},
        )
        assert r.status_code == 403
        body = r.json()
        assert body.get("code") == "PRODUCT_MODULE_DISABLED"

    def test_social_takeover_forbidden(self, client):
        rec = session_service.create_session(user_id="op2", email="op2@example.com", role="admin", permissions=None)
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
        r = client.post(
            "/api/live-chat/takeover",
            json={
                "conversation_id": "c1",
                "user_id": "instagram:12345",
                "operator_id": "ignored",
            },
            headers={"X-CSRF-Token": rec.csrf_token},
        )
        assert r.status_code == 403

    def test_session_idor_blocked(self, client):
        rec = session_service.create_session(
            user_id="real-user", email="real@example.com", role="admin", permissions=None
        )
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        r = client.get("/api/auth/session/other-user")
        assert r.status_code == 200
        assert r.json().get("success") is False

    def test_csrf_required_on_mutation(self, client):
        rec = session_service.create_session(user_id="op3", email="op3@example.com", role="admin", permissions=None)
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
        r = client.post("/api/smart-messaging/toggle", json={})
        assert r.status_code == 403

    def test_csrf_mismatch_still_403(self, client):
        rec = session_service.create_session(user_id="op3b", email="op3b@example.com", role="admin", permissions=None)
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
        r = client.post(
            "/api/auth/logout",
            json={},
            headers={"X-CSRF-Token": "definitely-not-the-csrf-token"},
        )
        assert r.status_code == 403
        assert r.json().get("error") == "CSRF validation failed"

    def test_role_matrix_viewer_forbidden_users(self, client):
        rec = session_service.create_session(user_id="v1", email="v@example.com", role="viewer", permissions=None)
        client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
        r = client.get("/api/auth/users")
        assert r.status_code == 403
