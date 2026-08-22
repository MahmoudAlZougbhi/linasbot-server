"""Direct Instagram Login subscribed_apps contract and secret-safe telemetry."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from services.meta_app_registry import MetaAppRegistry
from services.meta_instagram_login_capabilities import binding_ready_for_comments, binding_ready_for_dm
from services.meta_instagram_login_config import INSTAGRAM_LOGIN_GRAPH_API_VERSION
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR,
    INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR,
    INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR,
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


def test_failed_status_never_treats_stale_fields_as_verified_authority(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="failed",
        webhook_fields=tuple(EXPECTED_FIELDS),
    )
    credential = registry.get_credential(binding)

    assert binding_ready_for_dm(binding, credential) is False
    assert binding_ready_for_comments(binding, credential) is False
    public = binding.public_dict()["webhook_subscription"]
    assert public["ready_for_dm"] is False
    assert public["ready_for_comments"] is False


@pytest.mark.asyncio
async def test_subscribe_once_posts_query_fields_not_json_body() -> None:
    captured: dict[str, Any] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["content_type"] = request.headers.get("content-type")
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = request.content
        captured["subscribed_fields"] = request.url.params.get("subscribed_fields")
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await _subscribe_once(
            ig_user_id=INSTAGRAM_ID,
            access_token=SECRET_TOKEN,
            subscribed_fields=tuple(EXPECTED_FIELDS),
            graph_api_version=INSTAGRAM_LOGIN_GRAPH_API_VERSION,
            client=client,
        )

    assert captured["method"] == "POST"
    assert captured["url"].startswith(
        f"https://graph.instagram.com/{INSTAGRAM_LOGIN_GRAPH_API_VERSION}/{INSTAGRAM_ID}/subscribed_apps?"
    )
    assert captured["subscribed_fields"] == ",".join(EXPECTED_FIELDS)
    assert captured["body"] in {b"", None}
    assert not str(captured["content_type"] or "").startswith("application/json")
    assert captured["authorization"] == f"Bearer {SECRET_TOKEN}"


@pytest.mark.asyncio
async def test_ensure_get_first_skips_write_when_provider_already_ready(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
    credential = registry.get_credential(binding)
    observed: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        observed.append(f"{request.method} {request.url.path}")
        if request.method == "POST":
            raise AssertionError("subscribed_apps write must not run when GET already proves fields")
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

    assert observed == [f"GET /{INSTAGRAM_LOGIN_GRAPH_API_VERSION}/{INSTAGRAM_ID}/subscribed_apps"]
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
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
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


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [200, 500])
async def test_verify_rate_limit_stops_after_one_post_and_one_get(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
) -> None:
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", record_sleep)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
    credential = registry.get_credential(binding)
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            status_code,
            json={"error": {"type": "IGApiException", "code": 613, "is_transient": False}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET"]
    assert sleeps == []
    assert state.status == "failed"
    assert state.error == INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.webhook_subscribed_fields == ()
    assert binding_ready_for_dm(refreshed, credential) is False
    assert binding_ready_for_comments(refreshed, credential) is False


@pytest.mark.asyncio
async def test_verify_eventual_consistency_retries_reads_without_second_post(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", record_sleep)
    binding = _binding(registry, auth_flow="instagram_login", scopes=FULL_SCOPES)
    credential = registry.get_credential(binding)
    methods: list[str] = []
    reads = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        reads += 1
        fields = ["messages", "messaging_postbacks"] if reads < 3 else EXPECTED_FIELDS
        return httpx.Response(200, json={"data": [{"id": INSTAGRAM_APP_ID, "subscribed_fields": fields}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET", "POST", "GET", "GET"]
    assert sleeps == [10.0]
    assert state.status == "ready"


@pytest.mark.asyncio
async def test_uncertain_post_can_be_proved_by_get_without_second_write(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(registry, auth_flow="instagram_login", scopes=FULL_SCOPES)
    credential = registry.get_credential(binding)
    methods: list[str] = []
    write_started = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal write_started
        methods.append(request.method)
        if request.method == "POST":
            write_started = True
            raise httpx.ReadTimeout("write acknowledgement lost", request=request)
        if not write_started:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200,
            json={"data": [{"id": INSTAGRAM_APP_ID, "subscribed_fields": EXPECTED_FIELDS}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET", "POST", "GET"]
    assert state.status == "ready"


@pytest.mark.asyncio
async def test_missing_success_ack_is_verified_without_second_write(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
    credential = registry.get_credential(binding)
    methods: list[str] = []
    write_started = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal write_started
        methods.append(request.method)
        if request.method == "POST":
            write_started = True
            return httpx.Response(200, json={})
        if not write_started:
            return httpx.Response(200, json={"data": []})
        return httpx.Response(
            200,
            json={"data": [{"id": INSTAGRAM_APP_ID, "subscribed_fields": EXPECTED_FIELDS}]},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET", "POST", "GET"]
    assert state.status == "ready"


@pytest.mark.asyncio
async def test_deterministic_post_rejection_never_reposts_or_verifies(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
    credential = registry.get_credential(binding)
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(400, json={"error": {"type": "OAuthException", "code": 10}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET"]
    assert state.status == "failed"
    assert state.error == INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR


@pytest.mark.asyncio
async def test_explicit_false_ack_is_a_deterministic_write_rejection(
    registry: MetaAppRegistry,
) -> None:
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
    credential = registry.get_credential(binding)
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json={"success": False})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET", "POST"]
    assert state.status == "failed"
    assert state.error == INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR


@pytest.mark.asyncio
async def test_unresolved_accepted_write_is_deferred_without_repost(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="pending",
        webhook_fields=(),
    )
    credential = registry.get_credential(binding)
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert methods == ["GET", "POST", "GET", "GET"]
    assert state.error == INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.webhook_subscribed_fields == ()
    assert binding_ready_for_dm(refreshed, credential) is False
    assert binding_ready_for_comments(refreshed, credential) is False


@pytest.mark.asyncio
async def test_deferred_comments_verification_preserves_verified_dm_fields(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    binding = _binding(registry, auth_flow="instagram_login", scopes=FULL_SCOPES)
    credential = registry.get_credential(binding)
    methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": INSTAGRAM_APP_ID,
                        "subscribed_fields": ["messages", "messaging_postbacks"],
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

    assert methods == ["GET", "POST", "GET", "GET"]
    assert state.status == "partial"
    assert state.ready_for_dm is True
    assert state.ready_for_comments is False
    assert set(state.verified_fields) == {"messages", "messaging_postbacks"}
    assert state.error == INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR


@pytest.mark.asyncio
async def test_transient_verify_failure_preserves_prior_partial_dm_proof(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="partial",
        webhook_fields=("messages", "messaging_postbacks"),
    )
    credential = registry.get_credential(binding)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(500, json={"error": {"type": "IGApiException", "code": 2}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert state.status == "partial"
    assert state.error == INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR
    assert set(state.verified_fields) == {"messages", "messaging_postbacks"}
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert binding_ready_for_dm(refreshed, credential) is True
    assert binding_ready_for_comments(refreshed, credential) is False


@pytest.mark.asyncio
async def test_successful_empty_verify_clears_prior_partial_proof(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    binding = _binding(
        registry,
        auth_flow="instagram_login",
        scopes=FULL_SCOPES,
        webhook_status="partial",
        webhook_fields=("messages", "messaging_postbacks"),
    )
    credential = registry.get_credential(binding)

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"data": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        state = await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=registry,
            graph_api_version="v24.0",
            client=client,
        )

    assert state.status == "failed"
    assert state.verified_fields == ()
    refreshed = next(item for item in registry.list_bindings() if item.binding_id == binding.binding_id)
    assert refreshed.webhook_subscribed_fields == ()
    assert binding_ready_for_dm(refreshed, credential) is False
    assert binding_ready_for_comments(refreshed, credential) is False
