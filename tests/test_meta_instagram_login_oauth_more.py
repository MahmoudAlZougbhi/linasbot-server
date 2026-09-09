"""Instagram Login OAuth reauth, routing, and replay tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

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
    verify_instagram_login_webhook_signature,
)
from services.meta_instagram_login_oauth import (
    complete_instagram_login,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    InstagramLoginSubscriptionState,
)
from services.meta_multi_app_router import resolve_registry_events
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_return import mobile_oauth_failure_reason
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionChangedError,
    MetaSubjectDeletionLease,
)
from tests.meta_instagram_login_oauth_support import (
    MESSAGING_SCOPES,
    _start_state,
    _transport,
)

pytest_plugins = ('tests.meta_instagram_login_oauth_support',)

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

    with pytest.raises(MetaOAuthError, match="after two checks"):
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
    assert provider_methods == ["GET", "GET", "POST", "GET", "GET"]
    assert "DELETE" not in provider_methods


@pytest.mark.asyncio
async def test_unexpected_subscription_exception_discards_staged_credential(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fail_subscription(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("registry persistence unavailable")

    monkeypatch.setattr(
        "services.meta_instagram_login_oauth_complete.ensure_instagram_login_webhook_subscription",
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


def test_webhook_signature_uses_instagram_login_secret(instagram_env: None) -> None:
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
