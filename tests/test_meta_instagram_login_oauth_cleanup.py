"""Instagram Login OAuth cleanup-marker and orphan-cleanup tests."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
)
from services.meta_instagram_login_oauth import (
    begin_instagram_login,
    complete_instagram_login,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    InstagramLoginSubscriptionState,
)
from services.meta_instagram_login_subscription_recovery import (
    retry_instagram_login_cleanup,
    retry_instagram_login_orphan_cleanup,
)
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_return import mobile_oauth_failure_reason
from tests.meta_instagram_login_oauth_support import (
    _stage_direct_binding,
    _start_state,
    _transport,
)

pytest_plugins = ('tests.meta_instagram_login_oauth_support',)

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
        "services.meta_instagram_login_oauth_tokens.time.time",
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
