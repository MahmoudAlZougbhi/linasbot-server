"""Instagram Login OAuth, subscription, and routing tests."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaCredentialError,
    MetaOAuthStateError,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
    META_INSTAGRAM_LOGIN_REQUIRED_SCOPES,
    instagram_login_config_status,
    instagram_login_webhook_callback_url,
    verify_instagram_login_webhook_signature,
)
from services.meta_instagram_login_oauth import (
    begin_instagram_login,
    complete_instagram_login,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    InstagramLoginSubscriptionState,
    subscribed_fields_for_granted_scopes,
)
from services.meta_instagram_login_subscription_recovery import (
    retry_instagram_login_cleanup,
    retry_instagram_login_orphan_cleanup,
)
from services.meta_multi_app_router import resolve_registry_events
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_return import mobile_oauth_failure_reason
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionChangedError,
    MetaSubjectDeletionLease,
    MetaSubjectDeletionLeaseBusyError,
    MetaSubjectDeletionStoreUnavailableError,
    meta_deletion_subject_hmac,
)
from tests.meta_compliance_helpers import _FakeFirestore, _set_fake_meta_deletion_request

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
    assert all(path.startswith("/v24.0/") for path in seen_subscription_paths)


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

    monkeypatch.setattr("services.meta_instagram_login_oauth.acquire_meta_oauth_subject_guard", fail_guard)
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
                            "subscribed_fields": ["messages", "messaging_postbacks", "comments"],
                        }
                    ]
                },
            )
        return response

    with pytest.raises(MetaOAuthError, match="verification is still pending") as captured:
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
    assert provider_methods == ["GET", "POST", "GET", "GET", "GET"]
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

    with pytest.raises(MetaOAuthError, match="verification is still pending") as captured:
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
    assert provider_methods == ["GET", "POST", "GET", "GET", "GET"]
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

    with pytest.raises(MetaOAuthError, match="temporarily limiting") as captured:
        await complete_instagram_login(
            code="rate-limited-auth-code",
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
    assert provider_methods == ["GET", "POST", "GET"]
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

    with pytest.raises(MetaOAuthError, match="temporarily limiting") as captured:
        await complete_instagram_login(
            code="preflight-rate-limited-auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert mobile_oauth_failure_reason(captured.value) == "provider"
    assert provider_methods == ["GET"]
    assert all(
        item.status != "active"
        for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        if item.auth_flow == "instagram_login"
    )


@pytest.mark.asyncio
async def test_uncertain_post_acknowledgement_stays_durable_until_lifecycle(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_delay: float) -> None:
        return None

    monkeypatch.setattr("services.meta_instagram_login_subscription.asyncio.sleep", no_sleep)
    state = _start_state(registry)
    provider_methods: list[str] = []
    base_transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
            if request.method == "POST":
                return httpx.Response(204)
            return httpx.Response(200, json={"data": []})
        return await base_transport.handle_async_request(request)

    with pytest.raises(MetaOAuthError, match="verification is still pending"):
        await complete_instagram_login(
            code="uncertain-write-auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert binding.status == "testing"
    assert binding.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    assert registry.binding_credential_is_available(binding.binding_id)
    assert provider_methods == ["GET", "POST", "GET", "GET", "GET"]
    assert "DELETE" not in provider_methods


@pytest.mark.asyncio
async def test_unexpected_subscription_exception_discards_staged_credential(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_subscription(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("registry persistence unavailable")

    monkeypatch.setattr(
        "services.meta_instagram_login_oauth.ensure_instagram_login_webhook_subscription",
        fail_subscription,
    )
    state = _start_state(registry)
    with pytest.raises(RuntimeError, match="registry persistence unavailable"):
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=_transport(),
                base_url="https://graph.instagram.com",
            ),
        )

    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert binding.status == "disconnected"
    with pytest.raises(MetaCredentialError):
        registry.get_credential(binding)


@pytest.mark.asyncio
async def test_subject_change_after_instagram_subscription_discards_staged_credential(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def changed(_lease: MetaSubjectDeletionLease) -> None:
        raise MetaSubjectDeletionChangedError("simulated None-to-completed request race")

    monkeypatch.setattr(MetaSubjectDeletionLease, "assert_oauth_snapshot_unchanged", changed)
    subscription_posts: list[str] = []
    transport = _transport()

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/subscribed_apps"):
            subscription_posts.append(request.url.path)
        return await transport.handle_async_request(request)

    state = _start_state(registry)
    with pytest.raises(MetaOAuthError, match="safety guard changed") as captured:
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(recording_handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert mobile_oauth_failure_reason(captured.value) == "guard"
    assert subscription_posts
    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert binding.status == "disconnected"
    with pytest.raises(MetaCredentialError):
        registry.get_credential(binding)


@pytest.mark.asyncio
async def test_failed_instagram_reauth_preserves_prior_ready_binding(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900001"
    prior = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="prior-working-token",
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=MESSAGING_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        status="active",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "comments"),
    )

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

    refreshed_prior = next(item for item in registry.list_bindings() if item.binding_id == prior.binding_id)
    assert refreshed_prior.status == "active"
    assert refreshed_prior.instagram_login_ready is True
    assert registry.get_credential(refreshed_prior).access_token == "prior-working-token"
    staged = [item for item in registry.list_bindings() if item.binding_id != prior.binding_id]
    assert len(staged) == 1
    assert staged[0].status == "disconnected"


@pytest.mark.asyncio
async def test_instagram_login_supersedes_linked_ig_but_preserves_facebook_page(
    registry: MetaAppRegistry,
) -> None:
    instagram_id = "17840000999900001"
    page_id = "112233445566778"
    facebook = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="facebook-page-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=(
                "pages_show_list",
                "pages_manage_metadata",
                "pages_read_engagement",
                "pages_messaging",
            ),
            authorized_meta_user_id="998877",
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        page_name="Clinic Page",
        auth_flow="facebook_login",
    )
    linked_instagram = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id=page_id,
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="page-linked-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=(
                "pages_show_list",
                "pages_manage_metadata",
                "pages_read_engagement",
                "instagram_manage_messages",
                "instagram_basic",
            ),
            authorized_meta_user_id="998877",
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        instagram_username="clinic_page_ig",
        auth_flow="facebook_login",
    )
    state = _start_state(registry)
    result = await complete_instagram_login(
        code="auth-code",
        state=state,
        registry=registry,
        client=httpx.AsyncClient(transport=_transport(), base_url="https://graph.instagram.com"),
    )
    bindings = [item for item in registry.list_bindings(include_inactive=False) if item.asset_id == instagram_id]
    assert len(bindings) == 1
    assert result.binding.auth_flow == "instagram_login"
    linked_after = next(item for item in registry.list_bindings() if item.binding_id == linked_instagram.binding_id)
    assert linked_after.status == "inactive"
    assert linked_after.superseded_by_binding_id == result.binding.binding_id
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after.status == "active"
    assert registry.get_credential(facebook_after).access_token == "facebook-page-token"


@pytest.mark.asyncio
async def test_resolve_registry_events_requires_ready_subscription(registry: MetaAppRegistry) -> None:
    from services.meta_app_registry import get_meta_app_configs

    instagram_id = "17840000999900001"
    registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id="",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="ig-login-token",
            token_app_id="1035856539045307",
            token_profile_id=instagram_id,
            scopes=MESSAGING_SCOPES,
            expires_at=int(time.time()) + 30 * 24 * 3600,
            authorized_meta_user_id="112233",
            auth_flow="instagram_login",
        ),
        actor_id="owner",
        instagram_username="clinic_ig",
        auth_flow="instagram_login",
        webhook_subscription_status="pending",
    )
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": instagram_id,
                "messaging": [
                    {
                        "sender": {"id": "sender-1"},
                        "recipient": {"id": instagram_id},
                        "timestamp": 1_700_000_000_000,
                        "message": {"mid": "mid-1", "text": "hello"},
                    }
                ],
            }
        ],
    }
    routed = await resolve_registry_events(
        payload,
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow="instagram_login",
    )
    assert routed == []

    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    from services.meta_instagram_login_subscription import InstagramLoginSubscriptionState

    registry.update_instagram_login_webhook_subscription(
        binding.binding_id,
        state=InstagramLoginSubscriptionState(
            status="ready",
            subscribed_fields=("messages", "messaging_postbacks"),
            verified_fields=("messages", "messaging_postbacks"),
        ),
        actor_id="test",
    )
    routed_ready = await resolve_registry_events(
        payload,
        app_config=get_meta_app_configs()[APP_A_KEY],
        registry=registry,
        auth_flow="instagram_login",
    )
    assert len(routed_ready) == 1
    assert routed_ready[0].settings.graph_base_url == "https://graph.instagram.com"
    assert "ig-login-token" not in json.dumps(routed_ready[0].event)


def test_webhook_signature_uses_instagram_secret_only(instagram_env: None) -> None:
    body = b'{"object":"instagram"}'
    good = hmac.new(b"instagram-app-secret-tests", body, hashlib.sha256).hexdigest()
    bad = hmac.new(b"app-a-secret-tests", body, hashlib.sha256).hexdigest()
    assert verify_instagram_login_webhook_signature(body, f"sha256={good}")
    assert not verify_instagram_login_webhook_signature(body, f"sha256={bad}")


@pytest.mark.asyncio
async def test_complete_instagram_login_rejects_replayed_state(registry: MetaAppRegistry) -> None:
    state = _start_state(registry)
    client = httpx.AsyncClient(transport=_transport(), base_url="https://graph.instagram.com")
    await complete_instagram_login(code="auth-code", state=state, registry=registry, client=client)
    with pytest.raises(MetaOAuthStateError):
        await complete_instagram_login(code="auth-code", state=state, registry=registry, client=client)


@pytest.mark.asyncio
async def test_activation_commit_ack_loss_keeps_new_exact_owner_without_compensation(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prior = _stage_direct_binding(registry, token="prior-token", status="active")
    registry.update_instagram_login_webhook_subscription(
        prior.binding_id,
        state=InstagramLoginSubscriptionState(
            status="ready",
            subscribed_fields=("messages", "messaging_postbacks", "comments"),
            verified_fields=("messages", "messaging_postbacks", "comments"),
        ),
        actor_id="test",
    )
    original_activate = registry.activate_staged_binding

    def commit_then_lose_ack(*args: object, **kwargs: object) -> None:
        original_activate(*args, **kwargs)
        prior_latest = next(item for item in registry.list_bindings() if item.binding_id == prior.binding_id)
        registry.set_binding_status(
            prior_latest.binding_id,
            status="disconnected",
            actor_id="concurrent-disconnect",
            expected_generation=prior_latest.generation,
        )
        raise ConnectionError("simulated activation acknowledgement loss")

    monkeypatch.setattr(registry, "activate_staged_binding", commit_then_lose_ack)
    provider_methods: list[str] = []
    transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
        return await transport.handle_async_request(request)

    result = await complete_instagram_login(
        code="auth-code",
        state=_start_state(registry),
        registry=registry,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://graph.instagram.com"),
    )

    assert result.binding.active
    assert result.binding.instagram_login_product_ready
    active = [
        item
        for item in registry.list_bindings(include_inactive=False, include_superseded=True)
        if item.channel == "instagram" and item.asset_id == result.binding.asset_id
    ]
    assert [item.binding_id for item in active] == [result.binding.binding_id]
    assert "DELETE" not in provider_methods


@pytest.mark.asyncio
async def test_staging_commit_ack_loss_archives_hidden_credential_before_provider_write(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_authorize = registry.authorize_oauth_asset

    def stage_then_lose_ack(*args: object, **kwargs: object) -> object:
        staged = original_authorize(*args, **kwargs)
        if kwargs.get("create_new_binding"):
            raise ConnectionError("simulated staging acknowledgement loss")
        return staged

    monkeypatch.setattr(registry, "authorize_oauth_asset", stage_then_lose_ack)
    provider_calls: list[str] = []
    transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_calls.append(request.method)
        return await transport.handle_async_request(request)

    with pytest.raises(ConnectionError, match="staging acknowledgement"):
        await complete_instagram_login(
            code="auth-code",
            state=_start_state(registry),
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    staged = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert staged.status == "disconnected"
    assert registry.binding_credential_is_available(staged.binding_id) is False
    assert provider_calls == []


@pytest.mark.asyncio
async def test_cross_tenant_owner_rejected_before_subscription_mutation(
    registry: MetaAppRegistry,
) -> None:
    owner = _stage_direct_binding(
        registry,
        token="other-tenant-token",
        status="active",
        tenant_id="tenant-b",
    )
    provider_calls: list[str] = []
    transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_calls.append(request.method)
        return await transport.handle_async_request(request)

    with pytest.raises(MetaBindingConflictError, match="another workspace"):
        await complete_instagram_login(
            code="auth-code",
            state=_start_state(registry),
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert provider_calls == []
    assert next(item for item in registry.list_bindings() if item.binding_id == owner.binding_id).active
    assert registry.get_credential(owner).access_token == "other-tenant-token"


@pytest.mark.asyncio
async def test_cancellation_after_provider_subscribe_is_shielded_and_archived(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_instagram_login_oauth as oauth

    actual_ensure = oauth.ensure_instagram_login_webhook_subscription
    provider_methods: list[str] = []
    transport = _transport()

    async def cancel_after_subscribe(*args: object, **kwargs: object) -> object:
        result = await actual_ensure(*args, **kwargs)
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await asyncio.sleep(0)
        return result

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
        return await transport.handle_async_request(request)

    monkeypatch.setattr(oauth, "ensure_instagram_login_webhook_subscription", cancel_after_subscribe)
    with pytest.raises(asyncio.CancelledError):
        await complete_instagram_login(
            code="auth-code",
            state=_start_state(registry),
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    staged = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert staged.status == "disconnected"
    assert registry.binding_credential_is_available(staged.binding_id) is False
    assert "DELETE" in provider_methods


@pytest.mark.asyncio
async def test_failed_compensation_persists_and_restart_finishes_cleanup(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_instagram_login_oauth as oauth

    page_id = "112233445566778"
    facebook = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="facebook-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=("pages_messaging",),
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        status="active",
        auth_flow="facebook_login",
    )

    def changed(_lease: MetaSubjectDeletionLease) -> None:
        raise MetaSubjectDeletionChangedError("force activation compensation")

    async def fail_cleanup(*_args: object, **_kwargs: object) -> None:
        raise MetaOAuthError("simulated provider cleanup outage")

    monkeypatch.setattr(MetaSubjectDeletionLease, "assert_oauth_snapshot_unchanged", changed)
    monkeypatch.setattr(oauth, "_compensate_failed_instagram_activation", fail_cleanup)
    provider_methods: list[str] = []
    transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            provider_methods.append(request.method)
        return await transport.handle_async_request(request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://graph.instagram.com")
    with pytest.raises(MetaOAuthError, match="cleanup failed"):
        await complete_instagram_login(
            code="auth-code",
            state=_start_state(registry),
            registry=registry,
            client=client,
        )

    marker = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert marker.active is False
    assert marker.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
    assert registry.binding_credential_is_available(marker.binding_id) is True

    restarted = MetaAppRegistry(
        store_path=registry.store_path,
        audit_path=registry.audit_path,
        master_secret="instagram-login-registry-secret-tests-1234567890",
    )
    recovered = await retry_instagram_login_cleanup(
        marker.binding_id,
        registry=restarted,
        client=client,
    )

    assert recovered.status == "disconnected"
    assert restarted.binding_credential_is_available(marker.binding_id) is False
    assert provider_methods[-3:] == ["GET", "DELETE", "GET"]
    facebook_after = next(item for item in restarted.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after.active
    assert restarted.get_credential(facebook_after).access_token == "facebook-token"


@pytest.mark.asyncio
async def test_stale_cleanup_marker_repairs_new_active_owner_without_restoring_old_preimage(
    registry: MetaAppRegistry,
) -> None:
    old = _stage_direct_binding(registry, token="stale-marker-token")
    old = registry.update_instagram_login_webhook_subscription(
        old.binding_id,
        state=InstagramLoginSubscriptionState(
            status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
            subscribed_fields=("messages",),
            verified_fields=("messages",),
            error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
        ),
        actor_id="cleanup-marker",
    )
    new_staged = _stage_direct_binding(registry, token="new-owner-token")
    new = registry.activate_staged_binding(
        new_staged.binding_id,
        actor_id="owner",
        expected_generation=new_staged.generation,
    )
    provider_fields: tuple[str, ...] = ("messages",)
    provider_calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal provider_fields
        authorization = request.headers.get("authorization", "")
        provider_calls.append((request.method, authorization))
        if request.method == "POST":
            provider_fields = ("messages", "messaging_postbacks", "comments")
            return httpx.Response(200, json={"success": True})
        if request.method == "DELETE":
            pytest.fail("a stale marker must never delete the new active owner's subscription")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1035856539045307",
                        "subscribed_fields": list(provider_fields),
                    }
                ]
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    recovered = await retry_instagram_login_cleanup(old.binding_id, registry=registry, client=client)

    assert recovered.status == "disconnected"
    assert registry.binding_credential_is_available(old.binding_id) is False
    new_after = next(item for item in registry.list_bindings() if item.binding_id == new.binding_id)
    assert new_after.active
    assert new_after.instagram_login_product_ready
    assert any(method == "POST" and auth == "Bearer new-owner-token" for method, auth in provider_calls)
    assert all(method != "DELETE" for method, _auth in provider_calls)


@pytest.mark.asyncio
async def test_stale_marker_transient_inspection_failure_does_not_downgrade_ready_active(
    registry: MetaAppRegistry,
) -> None:
    old = _stage_direct_binding(registry, token="stale-marker-token")
    old = registry.update_instagram_login_webhook_subscription(
        old.binding_id,
        state=InstagramLoginSubscriptionState(
            status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
            subscribed_fields=(),
            verified_fields=(),
            error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
        ),
        actor_id="cleanup-marker",
    )
    new_staged = _stage_direct_binding(registry, token="new-owner-token")
    new_staged = registry.update_instagram_login_webhook_subscription(
        new_staged.binding_id,
        state=InstagramLoginSubscriptionState(
            status="ready",
            subscribed_fields=("messages", "messaging_postbacks", "comments"),
            verified_fields=("messages", "messaging_postbacks", "comments"),
        ),
        actor_id="test",
    )
    new = registry.activate_staged_binding(
        new_staged.binding_id,
        actor_id="owner",
        expected_generation=new_staged.generation,
    )
    before = next(item for item in registry.list_bindings() if item.binding_id == new.binding_id)

    async def transient_failure(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadError("temporary Graph outage", request=request)

    with pytest.raises(MetaOAuthError, match="inspection failed"):
        await retry_instagram_login_cleanup(
            old.binding_id,
            registry=registry,
            client=httpx.AsyncClient(transport=httpx.MockTransport(transient_failure)),
        )

    after = next(item for item in registry.list_bindings() if item.binding_id == new.binding_id)
    assert after == before
    assert after.instagram_login_product_ready
    assert registry.binding_credential_is_available(old.binding_id) is True
    marker_after = next(item for item in registry.list_bindings() if item.binding_id == old.binding_id)
    assert marker_after.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS


@pytest.mark.asyncio
async def test_fresh_reconnect_is_not_blocked_by_revoked_cleanup_marker_token(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _stage_direct_binding(registry, token="revoked-old-token")
    marked = registry.update_instagram_login_webhook_subscription(
        old.binding_id,
        state=InstagramLoginSubscriptionState(
            status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
            subscribed_fields=(),
            verified_fields=(),
            error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
        ),
        actor_id="cleanup-marker",
    )
    monkeypatch.setattr(
        "services.meta_instagram_login_oauth.time.time",
        lambda: marked.created_at + 301.0,
    )
    seen_authorizations: list[str] = []
    transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/subscribed_apps"):
            authorization = request.headers.get("authorization", "")
            seen_authorizations.append(authorization)
            if authorization == "Bearer revoked-old-token":
                return httpx.Response(401, json={"error": {"message": "token revoked"}})
        return await transport.handle_async_request(request)

    result = await complete_instagram_login(
        code="fresh-auth-code",
        state=_start_state(registry),
        registry=registry,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://graph.instagram.com"),
    )

    assert result.binding.active
    assert result.binding.instagram_login_product_ready
    assert "Bearer revoked-old-token" not in seen_authorizations
    old_after = next(item for item in registry.list_bindings() if item.binding_id == old.binding_id)
    assert old_after.status == "disconnected"
    assert registry.binding_credential_is_available(old.binding_id) is False


def test_recent_cleanup_marker_blocks_repeat_tap_before_storing_oauth_state(
    registry: MetaAppRegistry,
) -> None:
    old = _stage_direct_binding(registry, token="cleanup-owned-token")
    registry.update_instagram_login_webhook_subscription(
        old.binding_id,
        state=InstagramLoginSubscriptionState(
            status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
            subscribed_fields=(),
            verified_fields=(),
            error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
        ),
        actor_id="cleanup-marker",
    )

    with pytest.raises(MetaOAuthError, match="cleanup is in progress") as captured:
        begin_instagram_login(tenant_id="tenant-a", actor_id="owner-a", registry=registry)

    assert mobile_oauth_failure_reason(captured.value) == "provider"
    payload = json.loads(registry.store_path.read_text(encoding="utf-8"))
    assert payload.get("oauth_states") in (None, {})


def test_cleanup_marker_does_not_block_another_tenant(
    registry: MetaAppRegistry,
) -> None:
    old = _stage_direct_binding(registry, token="cleanup-owned-token", tenant_id="tenant-a")
    registry.update_instagram_login_webhook_subscription(
        old.binding_id,
        state=InstagramLoginSubscriptionState(
            status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
            subscribed_fields=(),
            verified_fields=(),
            error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
        ),
        actor_id="cleanup-marker",
    )

    url = begin_instagram_login(tenant_id="tenant-b", actor_id="owner-b", registry=registry)
    assert parse_qs(urlparse(url).query)["state"]


@pytest.mark.asyncio
async def test_cleanup_marker_created_after_start_blocks_callback_before_provider_write(
    registry: MetaAppRegistry,
) -> None:
    state = _start_state(registry)
    old = _stage_direct_binding(registry, token="cleanup-owned-token")
    registry.update_instagram_login_webhook_subscription(
        old.binding_id,
        state=InstagramLoginSubscriptionState(
            status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
            subscribed_fields=(),
            verified_fields=(),
            error=INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
        ),
        actor_id="cleanup-marker",
    )
    observed_requests: list[httpx.Request] = []
    transport = _transport()

    async def handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return await transport.handle_async_request(request)

    with pytest.raises(MetaOAuthError, match="cleanup is in progress") as captured:
        await complete_instagram_login(
            code="racing-cleanup-auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert mobile_oauth_failure_reason(captured.value) == "provider"
    assert not any(
        request.method == "POST" and request.url.path.endswith("/subscribed_apps") for request in observed_requests
    )


@pytest.mark.asyncio
async def test_orphan_cleanup_without_active_owner_deletes_provider_then_archives(
    registry: MetaAppRegistry,
) -> None:
    orphan = _stage_direct_binding(registry, token="orphan-token")
    present = True
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal present
        calls.append((request.method, request.headers.get("authorization", "")))
        if request.method == "DELETE":
            present = False
            return httpx.Response(200, json={"success": True})
        rows = (
            [
                {
                    "id": "1035856539045307",
                    "subscribed_fields": ["messages", "messaging_postbacks", "comments"],
                }
            ]
            if present
            else []
        )
        return httpx.Response(200, json={"data": rows})

    recovered = await retry_instagram_login_orphan_cleanup(
        orphan.binding_id,
        registry=registry,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert recovered.status == "disconnected"
    assert registry.binding_credential_is_available(orphan.binding_id) is False
    assert any(method == "DELETE" and auth == "Bearer orphan-token" for method, auth in calls)
    assert calls[-1][0] == "GET"


@pytest.mark.asyncio
async def test_orphan_cleanup_preserves_new_active_direct_and_facebook_owner(
    registry: MetaAppRegistry,
) -> None:
    page_id = "112233445566778"
    facebook = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="facebook-token",
            token_app_id="2963733803971681",
            token_profile_id=page_id,
            scopes=("pages_messaging",),
            auth_flow="facebook_login",
        ),
        actor_id="owner",
        status="active",
        auth_flow="facebook_login",
    )
    orphan = _stage_direct_binding(registry, token="old-orphan-token")
    new_staged = _stage_direct_binding(registry, token="new-active-token")
    new_staged = registry.update_instagram_login_webhook_subscription(
        new_staged.binding_id,
        state=InstagramLoginSubscriptionState(
            status="ready",
            subscribed_fields=("messages", "messaging_postbacks", "comments"),
            verified_fields=("messages", "messaging_postbacks", "comments"),
        ),
        actor_id="test",
    )
    active = registry.activate_staged_binding(
        new_staged.binding_id,
        actor_id="owner",
        expected_generation=new_staged.generation,
    )
    calls: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.headers.get("authorization", "")))
        if request.method == "DELETE":
            pytest.fail("orphan cleanup must not delete the new active subscription")
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "1035856539045307",
                        "subscribed_fields": ["messages", "messaging_postbacks", "comments"],
                    }
                ]
            },
        )

    await retry_instagram_login_orphan_cleanup(
        orphan.binding_id,
        registry=registry,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    assert registry.binding_credential_is_available(orphan.binding_id) is False
    active_after = next(item for item in registry.list_bindings() if item.binding_id == active.binding_id)
    assert active_after.active and active_after.instagram_login_product_ready
    assert calls == [("GET", "Bearer new-active-token")]
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after.active
    assert registry.get_credential(facebook_after).access_token == "facebook-token"
