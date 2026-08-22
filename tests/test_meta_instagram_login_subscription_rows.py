"""Instagram Login subscribed_apps GET row matching and Graph version."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from services.meta_app_registry import MetaAppRegistry
from services.meta_instagram_login_config import INSTAGRAM_LOGIN_GRAPH_API_VERSION
from services.meta_instagram_login_subscription import ensure_instagram_login_webhook_subscription
from services.meta_instagram_login_subscription_graph import parse_subscription_snapshot
from tests.meta_instagram_login_lifecycle_helpers import FULL_SCOPES, INSTAGRAM_ID, _binding

INSTAGRAM_APP_ID = "1035856539045307"
FACEBOOK_APP_ID = "2963733803971681"
EXPECTED_FIELDS = ["messages", "messaging_postbacks", "comments"]


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", FACEBOOK_APP_ID)
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", INSTAGRAM_APP_ID)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-row-match-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-row-match-secret-tests-1234567890",
    )


def test_parse_accepts_nested_application_id(instagram_env: None) -> None:
    snapshot = parse_subscription_snapshot(
        {
            "data": [
                {
                    "application": {"id": INSTAGRAM_APP_ID, "name": "Linas AI - IG"},
                    "subscribed_fields": EXPECTED_FIELDS,
                }
            ]
        }
    )
    assert snapshot == tuple(sorted(EXPECTED_FIELDS))


def test_parse_accepts_parent_facebook_app_id(instagram_env: None) -> None:
    snapshot = parse_subscription_snapshot(
        {
            "data": [
                {
                    "id": FACEBOOK_APP_ID,
                    "subscribed_fields": "messages,messaging_postbacks,comments",
                }
            ]
        }
    )
    assert snapshot == tuple(sorted(EXPECTED_FIELDS))


@pytest.mark.asyncio
async def test_ensure_uses_instagram_graph_v26_not_facebook_v24(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(registry, auth_flow="instagram_login", scopes=FULL_SCOPES)
    credential = registry.get_credential(binding)
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": INSTAGRAM_APP_ID,
                        "subscribed_fields": EXPECTED_FIELDS,
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert state.status == "ready"
    assert seen
    assert all(f"/{INSTAGRAM_LOGIN_GRAPH_API_VERSION}/{INSTAGRAM_ID}/subscribed_apps" in url for url in seen)
    assert all("/v24.0/" not in url for url in seen)
