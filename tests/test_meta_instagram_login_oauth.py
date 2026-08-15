"""Instagram Login OAuth, subscription, and routing tests."""

from __future__ import annotations

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
    MetaBindingCredential,
    MetaCredentialError,
    MetaOAuthStateError,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
    META_INSTAGRAM_LOGIN_REQUIRED_SCOPES,
    instagram_login_config_status,
    verify_instagram_login_webhook_signature,
)
from services.meta_instagram_login_oauth import (
    begin_instagram_login,
    complete_instagram_login,
)
from services.meta_instagram_login_subscription import (
    subscribed_fields_for_granted_scopes,
)
from services.meta_multi_app_router import resolve_registry_events
from services.meta_oauth import MetaOAuthError
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionChangedError,
    MetaSubjectDeletionLease,
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


def _transport(*, subscription_ok: bool = True, comments_verified: bool = True) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
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
                return httpx.Response(200, json={"success": True})
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "1035856539045307",
                            "subscribed_fields": [
                                "messages",
                                "messaging_postbacks",
                                *(["comments"] if comments_verified else []),
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404, json={"error": {"message": "not found"}})

    return httpx.MockTransport(handler)


def test_instagram_login_config_requires_dedicated_secret(monkeypatch: pytest.MonkeyPatch) -> None:
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
async def test_pending_deletion_blocks_instagram_before_subscription_or_staging(
    registry: MetaAppRegistry,
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
        state="pending",
    )
    observed_requests: list[httpx.Request] = []
    transport = _transport()

    async def recording_handler(request: httpx.Request) -> httpx.Response:
        observed_requests.append(request)
        return await transport.handle_async_request(request)

    state = _start_state(registry)
    with pytest.raises(MetaOAuthError, match="blocked by a data deletion request"):
        await complete_instagram_login(
            code="pending-deletion-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(recording_handler),
                base_url="https://graph.instagram.com",
            ),
        )

    assert registry.list_bindings() == []
    assert not any(
        request.method == "POST" and request.url.path.endswith("/subscribed_apps") for request in observed_requests
    )


@pytest.mark.asyncio
async def test_complete_instagram_login_rejects_fields_from_another_app(registry: MetaAppRegistry) -> None:
    state = _start_state(registry)

    async def handler(request: httpx.Request) -> httpx.Response:
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

    with pytest.raises(MetaOAuthError, match="webhook subscription could not be confirmed"):
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://graph.instagram.com",
            ),
        )


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
) -> None:
    state = _start_state(registry)
    with pytest.raises(MetaOAuthError, match="webhook subscription could not be confirmed"):
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=_transport(comments_verified=False),
                base_url="https://graph.instagram.com",
            ),
        )

    binding = next(item for item in registry.list_bindings() if item.auth_flow == "instagram_login")
    assert binding.status == "disconnected"
    with pytest.raises(MetaCredentialError):
        registry.get_credential(binding)


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
    with pytest.raises(MetaOAuthError, match="deletion state changed"):
        await complete_instagram_login(
            code="auth-code",
            state=state,
            registry=registry,
            client=httpx.AsyncClient(
                transport=httpx.MockTransport(recording_handler),
                base_url="https://graph.instagram.com",
            ),
        )

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
async def test_instagram_login_does_not_overwrite_page_linked_binding(registry: MetaAppRegistry) -> None:
    instagram_id = "17840000999900001"
    registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=instagram_id,
        page_id="112233445566778",
        instagram_account_id=instagram_id,
        app_key=APP_A_KEY,
        credential=MetaBindingCredential(
            access_token="page-linked-token",
            token_app_id="2963733803971681",
            token_profile_id="112233445566778",
            scopes=("pages_messaging", "instagram_manage_messages", "instagram_basic"),
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
    assert len(bindings) == 2
    assert {item.auth_flow for item in bindings} == {"facebook_login", "instagram_login"}
    assert result.binding.auth_flow == "instagram_login"


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
