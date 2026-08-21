"""Instagram Login authorize URL must force reauth (Meta mobile guidance)."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from services.meta_app_registry import MetaAppRegistry
from services.meta_instagram_login_oauth import begin_instagram_login
from tests.meta_compliance_helpers import _FakeFirestore


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv(
        "META_INSTAGRAM_LOGIN_REDIRECT_URI",
        "https://www.linasaibot.com/oauth/instagram/callback",
    )
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-registry-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    import utils.utils

    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: _FakeFirestore())
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-registry-secret-tests-1234567890",
    )


def test_instagram_authorize_url_forces_reauth_for_mobile(registry: MetaAppRegistry) -> None:
    url = begin_instagram_login(tenant_id="tenant-a", actor_id="owner-a", registry=registry)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.hostname == "www.instagram.com"
    assert query["force_reauth"] == ["true"]
    assert query["response_type"] == ["code"]
    assert "instagram_business_basic" in (query.get("scope") or [""])[0]
