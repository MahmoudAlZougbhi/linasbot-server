"""Instagram Login OAuth config, completion, and preflight tests."""

from __future__ import annotations

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaCredentialError,
)
from services.meta_instagram_login_config import (
    INSTAGRAM_LOGIN_GRAPH_API_VERSION,
    META_INSTAGRAM_LOGIN_REQUIRED_SCOPES,
    instagram_login_config_status,
    instagram_login_webhook_callback_url,
)
from services.meta_instagram_login_oauth import (
    complete_instagram_login,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    subscribed_fields_for_granted_scopes,
)
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_return import mobile_oauth_failure_reason
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionLease,
    MetaSubjectDeletionLeaseBusyError,
    MetaSubjectDeletionStoreUnavailableError,
    meta_deletion_subject_hmac,
)
from tests.meta_compliance_helpers import _FakeFirestore, _set_fake_meta_deletion_request
from tests.meta_instagram_login_oauth_support import (
    MESSAGING_SCOPES,
    _start_state,
    _transport,
)

pytest_plugins = ("tests.meta_instagram_login_oauth_support",)


def test_instagram_login_config_accepts_apex_public_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "dedicated-instagram-secret")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_REDIRECT_URI", "https://www.linasaibot.com/oauth/instagram/callback")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_PATH", "/webhook/instagram-login")
    monkeypatch.setenv("PUBLIC_URL", "https://linasaibot.com")

    status = instagram_login_config_status()

    assert status.configured is True
    assert instagram_login_webhook_callback_url() == ("https://www.linasaibot.com/webhook/instagram-login")

    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.delenv("META_INSTAGRAM_LOGIN_APP_SECRET", raising=False)
    status = instagram_login_config_status()
    assert not status.configured
    assert "META_INSTAGRAM_LOGIN_APP_SECRET" in status.missing


@pytest.mark.parametrize(
    ("name", "value", "missing_key"),
    [
        ("META_INSTAGRAM_LOGIN_REDIRECT_URI", "https://wrong.example/callback", "META_INSTAGRAM_LOGIN_REDIRECT_URI"),
        ("META_INSTAGRAM_LOGIN_WEBHOOK_PATH", "/webhook/wrong", "META_INSTAGRAM_LOGIN_WEBHOOK_PATH"),
        ("PUBLIC_URL", "https://wrong.example", "PUBLIC_URL"),
    ],
)
def test_instagram_login_config_rejects_foreign_callback_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
    missing_key: str,
) -> None:
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_ID", "1035856539045307")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_APP_SECRET", "dedicated-instagram-secret")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN", "verify-ig-login-tests")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_REDIRECT_URI", "https://www.linasaibot.com/oauth/instagram/callback")
    monkeypatch.setenv("META_INSTAGRAM_LOGIN_WEBHOOK_PATH", "/webhook/instagram-login")
    monkeypatch.setenv("PUBLIC_URL", "https://www.linasaibot.com")
    monkeypatch.setenv(name, value)

    status = instagram_login_config_status()

    assert status.configured is False
    assert missing_key in status.missing


def test_subscribed_fields_include_comments_only_when_scope_granted() -> None:
    base = subscribed_fields_for_granted_scopes(MESSAGING_SCOPES[:2])
    with_comments = subscribed_fields_for_granted_scopes(MESSAGING_SCOPES)
    assert "comments" not in base
    assert "comments" in with_comments


def test_instagram_login_activation_requires_dm_and_comments_scope() -> None:
    assert META_INSTAGRAM_LOGIN_REQUIRED_SCOPES == frozenset(MESSAGING_SCOPES)


@pytest.mark.asyncio
async def test_complete_instagram_login_subscribes_and_marks_ready(registry: MetaAppRegistry) -> None:
    state = _start_state(registry)
    seen_subscription_paths: list[str] = []
    transport = _transport()

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            seen_subscription_paths.append(request.url.path)
        return await transport.handle_async_request(request)

    result = await complete_instagram_login(
        code="auth-code",
        state=state,
        registry=registry,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(recording_handler),
            base_url="https://graph.instagram.com",
        ),
    )
    assert result.binding.auth_flow == "instagram_login"
    assert result.binding.webhook_subscription_status == "ready"
    assert result.binding.instagram_login_ready is True
    stored = registry.store_path.read_text(encoding="utf-8")
    assert "long-lived-token" not in stored
    assert seen_subscription_paths
    assert all(path.startswith(f"/{INSTAGRAM_LOGIN_GRAPH_API_VERSION}/") for path in seen_subscription_paths)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("deletion_state", "expected_reason"),
    [("pending", "deletion"), ("failed", "deletion_failed")],
)
async def test_deletion_blocks_instagram_before_subscription_or_staging(
    registry: MetaAppRegistry,
    deletion_state: str,
    expected_reason: str,
) -> None:
    import utils.utils

    db = utils.utils.get_firestore_db()
    assert isinstance(db, _FakeFirestore)
    subject_key = meta_deletion_subject_hmac(
        app_key=APP_A_KEY,
        app_id="1035856539045307",
        auth_flow="instagram_login",
        meta_user_id="17840000999900001",
        app_secret="instagram-app-secret-tests",
    )
    _set_fake_meta_deletion_request(
        db,
        subject_key=subject_key,
        app_key=APP_A_KEY,
        app_id="1035856539045307",
        auth_flow="instagram_login",
        state=deletion_state,
    )
    observed_requests: list[httpx.Request] = []
    transport = _transport()

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return await transport.handle_async_request(request)

    oauth_state = _start_state(registry)
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(recording_handler),
        base_url="https://graph.instagram.com",
    ) as client:
        with pytest.raises(
            MetaOAuthError,
            match=rf"blocked by a {deletion_state} data deletion request",
        ) as captured:
            await complete_instagram_login(
                code=f"{deletion_state}-deletion-code",
                state=oauth_state,
                registry=registry,
                client=client,
            )

    assert mobile_oauth_failure_reason(captured.value) == expected_reason
    assert registry.list_bindings() == []
    assert not any(
        request.method == "POST" and request.url.path.endswith("/subscribed_apps") for request in observed_requests
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "expected_reason"),
    [
        (MetaSubjectDeletionStoreUnavailableError("Meta subject lease transaction failed"), "guard"),
        (MetaSubjectDeletionLeaseBusyError("Meta subject lease is busy"), "busy"),
    ],
)
async def test_subject_guard_failures_are_not_reported_as_data_deletion(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    expected_reason: str,
) -> None:
    observed_requests: list[httpx.Request] = []
    transport = _transport()

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return await transport.handle_async_request(request)

    def fail_guard(*_args: object, **_kwargs: object) -> MetaSubjectDeletionLease:
        if isinstance(failure, MetaSubjectDeletionStoreUnavailableError):
            try:
                raise ValueError("Transaction not in progress, cannot be used in API requests")
            except ValueError as cause:
                raise failure from cause
        raise failure

    monkeypatch.setattr("services.meta_instagram_login_oauth_complete.acquire_meta_oauth_subject_guard", fail_guard)
    state = _start_state(registry)
    with pytest.raises(MetaOAuthError) as captured:
        await complete_instagram_login(
            code="guard-failure-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(recording_handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert "data deletion" not in str(captured.value).lower()
    assert mobile_oauth_failure_reason(captured.value) == expected_reason
    assert registry.list_bindings() == []
    assert not any(
        request.method == "POST" and request.url.path.endswith("/subscribed_apps") for request in observed_requests
    )


@pytest.mark.asyncio
async def test_complete_instagram_login_rejects_fields_from_another_app(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    state = _start_state(registry)
    provider_methods: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
        response = await _transport().handle_async_request(request)
        if request.method == "GET" and request.url.path.endswith("/subscribed_apps"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "9999999999999999",
                            "subscribed_fields": ["messages"],
                        }
                    ]
                },
            )
        return response

    with pytest.raises(MetaOAuthError, match="after two checks") as captured:
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )
    assert mobile_oauth_failure_reason(captured.value) == "provider"
    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert binding.status == "testing"
    assert binding.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    assert registry.binding_credential_is_available(binding.binding_id)
    assert provider_methods == ["GET", "GET", "POST", "GET", "GET"]
    assert "DELETE" not in provider_methods


@pytest.mark.asyncio
async def test_complete_instagram_login_fails_closed_when_subscription_missing(registry: MetaAppRegistry) -> None:
    state = _start_state(registry)
    with pytest.raises(MetaOAuthError, match="webhook subscription could not be confirmed"):
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=_transport(subscription_ok=False),
                base_url="https://graph.instagram.com",
            ),
        )

    bindings = [item for item in registry.list_bindings() if item.auth_flow == "instagram_login"]
    assert len(bindings) == 1
    assert bindings[0].status == "disconnected"
    assert bindings[0].active is False
    with pytest.raises(MetaCredentialError):
        registry.get_credential(bindings[0])


@pytest.mark.asyncio
async def test_complete_instagram_login_fails_when_granted_comments_are_not_verified(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    state = _start_state(registry)
    provider_methods: list[str] = []
    transport = _transport(comments_verified=False)

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
        return await transport.handle_async_request(request)

    with pytest.raises(MetaOAuthError, match="after two checks") as captured:
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(recording_handler),
                base_url="https://graph.instagram.com",
            ),
        )

    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert mobile_oauth_failure_reason(captured.value) == "provider"
    assert binding.status == "testing"
    assert binding.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    assert registry.binding_credential_is_available(binding.binding_id)
    assert provider_methods == ["GET", "GET", "POST", "GET", "GET"]
    assert "DELETE" not in provider_methods


@pytest.mark.asyncio
async def test_verify_rate_limit_persists_cleanup_without_hot_compensation(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    provider_methods: list[str] = []
    base_transport = _transport()
    reads = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal reads
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
            if request.method == "GET":
                reads += 1
                if reads == 2:
                    return httpx.Response(
                        500,
                        json={"error": {"type": "IGApiException", "code": 613, "is_transient": False}},
                    )
        return await base_transport.handle_async_request(request)

    with pytest.raises(MetaOAuthError, match="Graph error 613") as captured:
        await complete_instagram_login(
            code="rate-limited-auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert mobile_oauth_failure_reason(captured.value) == "rate_limit"
    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert binding.status == "testing"
    assert binding.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    assert registry.binding_credential_is_available(binding.binding_id)
    assert provider_methods == ["GET", "GET"]
    assert "DELETE" not in provider_methods


@pytest.mark.asyncio
async def test_preflight_rate_limit_returns_provider_guidance_without_write(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    provider_methods: list[str] = []
    base_transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
            return httpx.Response(
                500,
                json={"error": {"type": "IGApiException", "code": 613, "is_transient": False}},
            )
        return await base_transport.handle_async_request(request)

    with pytest.raises(MetaOAuthError, match="Graph error 613") as captured:
        await complete_instagram_login(
            code="preflight-rate-limited-auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert mobile_oauth_failure_reason(captured.value) == "rate_limit"
    assert provider_methods == ["GET"]
    assert all(
        item.status != "active"
        for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        if item.auth_flow == "instagram_login"
    )
