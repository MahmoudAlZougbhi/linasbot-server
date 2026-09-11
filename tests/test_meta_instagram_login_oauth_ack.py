"""Instagram Login OAuth ack-loss, cancel, and compensation tests."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingConflictError,
    MetaBindingCredential,
)
from services.meta_instagram_login_oauth import (
    complete_instagram_login,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    InstagramLoginSubscriptionState,
)
from services.meta_instagram_login_subscription_recovery import (
    retry_instagram_login_cleanup,
)
from services.meta_oauth import MetaOAuthError
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionChangedError,
    MetaSubjectDeletionLease,
)
from tests.meta_instagram_login_oauth_support import (
    _stage_direct_binding,
    _start_state,
    _transport,
)

pytest_plugins = ("tests.meta_instagram_login_oauth_support",)


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
    import services.meta_instagram_login_oauth_complete as oauth

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
    import services.meta_instagram_login_oauth_complete as oauth

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
