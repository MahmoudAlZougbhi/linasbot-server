"""Shared fixtures and helpers for Instagram Login OAuth tests."""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
)
from services.meta_instagram_login_oauth import (
    begin_instagram_login,
)
from tests.meta_compliance_helpers import _FakeFirestore

INSTAGRAM_SCOPES = tuple(sorted(META_INSTAGRAM_LOGIN_REQUEST_SCOPES))
MESSAGING_SCOPES = (
    "instagram_business_basic",
    "instagram_business_manage_messages",
    "instagram_business_manage_comments",
)


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
    # Other test modules configure PUBLIC_URL for their own webhook products at
    # collection time.  Keep this fixture isolated to the exact Direct-IG
    # callback boundary that production enforces.
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-registry-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-registry-secret-tests-1234567890",
    )


def _start_state(registry: MetaAppRegistry) -> str:
    url = begin_instagram_login(tenant_id="tenant-a", actor_id="owner-a", registry=registry)
    return parse_qs(urlparse(url).query)["state"][0]


def _stage_direct_binding(
    registry: MetaAppRegistry,
    *,
    token: str,
    status: str = "testing",
    tenant_id: str = "tenant-a",
) -> MetaAssetBinding:
    instagram_id = "17840000999900001"
    return registry.authorize_oauth_asset(
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token=token,
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=MESSAGING_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        status=status,
        auth_flow="instagram_login",
        webhook_subscription_status="pending",
        create_new_binding=status == "testing",
    )


def _transport(*, subscription_ok: bool = True, comments_verified: bool = True) -> httpx.MockTransport:
    subscribed = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal subscribed
        path = request.url.path
        if path.endswith("/oauth/access_token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "short-lived-token",
                    "user_id": "17840000999900001",
                    "granted_scopes": ",".join(MESSAGING_SCOPES),
                },
            )
        if path.endswith("/access_token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "long-lived-token",
                    "token_type": "bearer",
                    "expires_in": 5_183_944,
                    "granted_scopes": ",".join(MESSAGING_SCOPES),
                },
            )
        if path.endswith("/me"):
            return httpx.Response(
                200,
                json={"user_id": "17840000999900001", "username": "clinic_ig", "id": "17840000999900001"},
            )
        if path.endswith("/subscribed_apps"):
            if request.method == "POST":
                if not subscription_ok:
                    return httpx.Response(400, json={"error": {"message": "subscription failed"}})
                subscribed = True
                return httpx.Response(200, json={"success": True})
            if request.method == "DELETE":
                subscribed = False
                return httpx.Response(200, json={"success": True})
            return httpx.Response(
                200,
                json={
                    "data": (
                        [
                            {
                                "id": "1035856539045307",
                                "subscribed_fields": [
                                    "messages",
                                    "messaging_postbacks",
                                    *(["comments"] if comments_verified else []),
                                ],
                            }
                        ]
                        if subscribed
                        else []
                    )
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)
