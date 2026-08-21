"""Direct Instagram Login subscribed_apps JSON contract and secret-safe telemetry."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from services.meta_app_registry import MetaAppRegistry
from services.meta_instagram_login_subscription import (
    _subscribe_once,
    ensure_instagram_login_webhook_subscription,
)
from services.meta_oauth_graph_http import MetaOAuthError
from tests.meta_instagram_login_lifecycle_helpers import FULL_SCOPES, INSTAGRAM_ID, _binding

INSTAGRAM_APP_ID = "1035856539045307"
SECRET_TOKEN = "IGQW-secret-access-token-must-not-appear"
SECRET_ERROR_MESSAGE = "User token IGQW-secret-access-token-must-not-appear is invalid"
EXPECTED_FIELDS = ["messages", "messaging_postbacks", "comments"]


@pytest.fixture
def instagram_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_MULTI_APP_REGISTRY_ENABLED", "true")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_A_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", INSTAGRAM_APP_ID)
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "instagram-app-secret-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "instagram-login-subscription-secret-tests-1234567890")


@pytest.fixture
def registry(tmp_path: Path, instagram_env: None) -> MetaAppRegistry:
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="instagram-login-subscription-secret-tests-1234567890",
    )


def _rendered_logs(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def _assert_no_secret_leakage(rendered: str) -> None:
    assert SECRET_TOKEN not in rendered
    assert SECRET_ERROR_MESSAGE not in rendered
    assert "Authorization" not in rendered
    assert "Bearer" not in rendered
    assert INSTAGRAM_ID not in rendered
    assert "graph.instagram.com" not in rendered


@pytest.mark.asyncio
async def test_subscribe_once_posts_json_array_not_form() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("content-type")
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await _subscribe_once(
            ig_user_id=INSTAGRAM_ID,
            access_token=SECRET_TOKEN,
            subscribed_fields=tuple(EXPECTED_FIELDS),
            graph_api_version="v24.0",
            client=client,
        )

    assert captured["method"] == "POST"
    assert captured["url"] == (f"https://graph.instagram.com/v24.0/{INSTAGRAM_ID}/subscribed_apps")
    assert str(captured["content_type"]).startswith("application/json")
    assert captured["body"] == {"subscribed_fields": EXPECTED_FIELDS}
    assert captured["authorization"] == f"Bearer {SECRET_TOKEN}"
    assert isinstance(captured["body"]["subscribed_fields"], list)
    assert captured["body"]["subscribed_fields"] != ",".join(EXPECTED_FIELDS)


@pytest.mark.asyncio
async def test_ensure_posts_json_then_get_verifies_instagram_product_row(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(registry, auth_flow="instagram_login", scopes=FULL_SCOPES)
    credential = registry.get_credential(binding)
    observed: list[tuple[str, str, dict[str, Any] | None]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] | None = None
        if request.method == "POST":
            assert request.headers.get("content-type", "").startswith("application/json")
            body = json.loads(request.content)
        observed.append((request.method, str(request.url), body))
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": INSTAGRAM_APP_ID,
                        "subscribed_fields": list(EXPECTED_FIELDS),
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

    assert [method for method, _url, _body in observed] == ["POST", "GET"]
    post_method, post_url, post_body = observed[0]
    get_method, get_url, get_body = observed[1]
    assert post_method == "POST"
    assert get_method == "GET"
    assert post_url == f"https://graph.instagram.com/v24.0/{INSTAGRAM_ID}/subscribed_apps"
    assert get_url == f"https://graph.instagram.com/v24.0/{INSTAGRAM_ID}/subscribed_apps"
    assert post_body == {"subscribed_fields": EXPECTED_FIELDS}
    assert get_body is None
    assert state.status == "ready"
    assert state.ready_for_dm is True
    assert state.ready_for_comments is True
    assert list(state.subscribed_fields) == EXPECTED_FIELDS
    assert set(state.verified_fields) == set(EXPECTED_FIELDS)


@pytest.mark.asyncio
async def test_subscribe_failure_telemetry_omits_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == f"Bearer {SECRET_TOKEN}"
        return httpx.Response(
            400,
            headers={"x-fb-request-id": "AX-safe-request-id-123"},
            json={
                "error": {
                    "message": SECRET_ERROR_MESSAGE,
                    "type": "OAuthException",
                    "code": 190,
                    "error_subcode": 463,
                    "is_transient": False,
                    "fbtrace_id": "secret-fbtrace-must-not-appear",
                }
            },
        )

    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MetaOAuthError, match="failed with HTTP 400"):
            await _subscribe_once(
                ig_user_id=INSTAGRAM_ID,
                access_token=SECRET_TOKEN,
                subscribed_fields=tuple(EXPECTED_FIELDS),
                graph_api_version="v24.0",
                client=client,
            )

    rendered = _rendered_logs(caplog)
    assert "subscribed_apps stage=subscribe" in rendered
    assert "http_status=400" in rendered
    assert "error_type=OAuthException" in rendered
    assert "error_code=190" in rendered
    assert "error_subcode=463" in rendered
    assert "is_transient=false" in rendered
    assert "x_fb_request_id=AX-safe-request-id-123" in rendered
    assert "secret-fbtrace-must-not-appear" not in rendered
    _assert_no_secret_leakage(rendered)


@pytest.mark.asyncio
async def test_verify_failure_telemetry_omits_secrets(
    registry: MetaAppRegistry,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    binding = _binding(registry, auth_flow="instagram_login", scopes=FULL_SCOPES)
    credential = registry.get_credential(binding)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            403,
            headers={"x-fb-request-id": "AX-verify-request-id-456"},
            json={
                "error": {
                    "message": SECRET_ERROR_MESSAGE,
                    "type": "OAuthException",
                    "code": 10,
                    "error_subcode": 33,
                    "is_transient": True,
                }
            },
        )

    caplog.set_level(logging.WARNING, logger="uvicorn.error")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    rendered = _rendered_logs(caplog)
    assert state.status == "failed"
    assert "subscribed_apps stage=verify" in rendered
    assert "http_status=403" in rendered
    assert "error_type=OAuthException" in rendered
    assert "error_code=10" in rendered
    assert "error_subcode=33" in rendered
    assert "is_transient=true" in rendered
    assert "x_fb_request_id=AX-verify-request-id-456" in rendered
    _assert_no_secret_leakage(rendered)
    assert credential.access_token not in rendered
    assert SECRET_TOKEN not in state.error
    assert INSTAGRAM_ID not in state.error
    assert credential.access_token not in state.error
