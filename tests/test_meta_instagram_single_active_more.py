"""Instagram single-active disconnect and recovery tests."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest

from services.meta_app_registry import (
    MetaAppRegistry,
)
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.meta_instagram_login_subscription import ensure_instagram_login_webhook_subscription
from services.meta_oauth import MetaOAuthError
from services.mobile_integrations_display import bindings_for_disconnect
from tests.meta_instagram_single_active_support import (
    INSTAGRAM_ID,
    _activate_direct,
    _facebook_and_linked_instagram,
    _force_binding_fields,
    _patch_direct_provider_cleanup,
    _stage_direct_instagram,
)

pytest_plugins = ("tests.meta_instagram_single_active_support", "tests.meta_app_registry_fixtures")


@pytest.mark.asyncio
async def test_direct_instagram_disconnect_uses_exact_provider_endpoint(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    facebook, _linked, direct = _activate_direct(registry)
    facebook_before = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    facebook_token = registry.get_credential(facebook_before).access_token
    present = True
    calls: list[tuple[str, str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal present
        calls.append((request.method, str(request.url), request.headers.get("authorization", "")))
        assert request.url.host == "graph.instagram.com"
        assert request.url.path == f"/v26.0/{INSTAGRAM_ID}/subscribed_apps"
        if request.method == "GET":
            data = (
                [
                    {
                        "id": "1035856539045307",
                        "subscribed_fields": ["messages", "messaging_postbacks", "comments"],
                    }
                ]
                if present
                else []
            )
            return httpx.Response(200, json={"data": data})
        assert request.method == "DELETE"
        present = False
        return httpx.Response(200, json={"success": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        actual_disconnect = graph.disconnect_binding_webhook

        async def disconnect_with_client(binding: Any, *, actor_id: str, registry: MetaAppRegistry) -> Any:
            return await actual_disconnect(
                binding,
                actor_id=actor_id,
                registry=registry,
                client=client,
            )

        monkeypatch.setattr(
            "services.meta_connection_disconnect.disconnect_binding_webhook",
            disconnect_with_client,
        )
        targets = bindings_for_disconnect(
            "tenant-a",
            "instagram",
            asset_id=INSTAGRAM_ID,
            registry=registry,
        )
        await disconnect_meta_binding_set(
            targets,
            actor_id="owner",
            registry=registry,
            asset_id=INSTAGRAM_ID,
        )

    assert [method for method, _url, _authorization in calls] == ["GET", "DELETE", "GET"]
    assert all(authorization == "Bearer direct-ig-token-tenant-a" for _method, _url, authorization in calls)
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after == facebook_before
    assert registry.get_credential(facebook_after).access_token == facebook_token
    assert registry.binding_credential_is_available(direct.binding_id) is False


@pytest.mark.asyncio
async def test_direct_instagram_disconnect_accepts_already_absent_provider_subscription(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    staged = _stage_direct_instagram(registry)
    direct = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
    )

    async def absent(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def unexpected_delete(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("an already-absent direct subscription must not be deleted again")

    monkeypatch.setattr(graph, "inspect_instagram_login_webhook_subscription", absent)
    monkeypatch.setattr(graph, "unsubscribe_instagram_login_webhook_raw", unexpected_delete)

    disconnected = await graph.disconnect_binding_webhook(direct, actor_id="owner", registry=registry)

    assert disconnected.status == "disconnected"
    assert registry.binding_credential_is_available(direct.binding_id) is False


@pytest.mark.asyncio
async def test_direct_instagram_provider_failure_leaves_retry_credential_then_converges(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    staged = _stage_direct_instagram(registry)
    direct = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
    )

    async def provider_failure(*_args: Any, **_kwargs: Any) -> None:
        raise MetaOAuthError("simulated provider failure")

    monkeypatch.setattr(graph, "inspect_instagram_login_webhook_subscription", provider_failure)
    with pytest.raises(MetaOAuthError, match="provider failure"):
        await graph.disconnect_binding_webhook(direct, actor_id="owner", registry=registry)

    partial = next(item for item in registry.list_bindings() if item.binding_id == direct.binding_id)
    assert partial.status == "disconnected"
    assert registry.binding_credential_is_available(partial.binding_id) is True

    provider_calls = _patch_direct_provider_cleanup(monkeypatch)
    settled = await graph.disconnect_binding_webhook(partial, actor_id="owner", registry=registry)
    assert settled.status == "disconnected"
    assert registry.binding_credential_is_available(settled.binding_id) is False
    assert provider_calls == ["inspect", "delete", "inspect"]


@pytest.mark.asyncio
async def test_stale_direct_disconnect_keeps_new_active_direct_subscription(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    old_staged = _stage_direct_instagram(registry)
    old = registry.activate_staged_binding(
        old_staged.binding_id,
        actor_id="owner",
        expected_generation=old_staged.generation,
    )
    old = registry.set_binding_status(
        old.binding_id,
        status="disconnected",
        actor_id="owner",
        expected_generation=old.generation,
    )
    new_staged = _stage_direct_instagram(registry)
    new = registry.activate_staged_binding(
        new_staged.binding_id,
        actor_id="owner",
        expected_generation=new_staged.generation,
    )

    async def unexpected_provider_call(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("the new active direct binding still owns the provider subscription")

    monkeypatch.setattr(graph, "inspect_instagram_login_webhook_subscription", unexpected_provider_call)
    monkeypatch.setattr(graph, "unsubscribe_instagram_login_webhook_raw", unexpected_provider_call)

    settled = await graph.disconnect_binding_webhook(old, actor_id="owner", registry=registry)

    assert registry.binding_credential_is_available(settled.binding_id) is False
    new_after = next(item for item in registry.list_bindings() if item.binding_id == new.binding_id)
    assert new_after.active
    assert registry.binding_credential_is_available(new_after.binding_id) is True


@pytest.mark.asyncio
async def test_direct_connect_waits_for_disconnect_lock_and_refuses_stale_resubscribe(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    staged = _stage_direct_instagram(registry)
    direct = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
    )
    credential = registry.get_credential(direct)
    cleanup_entered = asyncio.Event()
    release_cleanup = asyncio.Event()

    async def paused_cleanup(*_args: Any, **_kwargs: Any) -> None:
        cleanup_entered.set()
        await release_cleanup.wait()

    monkeypatch.setattr(graph, "_cleanup_binding_provider_subscription", paused_cleanup)
    disconnect_task = asyncio.create_task(graph.disconnect_binding_webhook(direct, actor_id="owner", registry=registry))
    await asyncio.wait_for(cleanup_entered.wait(), timeout=2)

    async def unexpected_http(_request: httpx.Request) -> httpx.Response:
        pytest.fail("stale subscribe must be rejected before reaching Instagram")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_http)) as client:
        subscribe_task = asyncio.create_task(
            ensure_instagram_login_webhook_subscription(
                direct,
                credential,
                registry=registry,
                graph_api_version="v24.0",
                client=client,
            )
        )
        await asyncio.sleep(0.05)
        assert subscribe_task.done() is False
        release_cleanup.set()
        await disconnect_task
        with pytest.raises(MetaOAuthError, match="binding changed"):
            await subscribe_task


@pytest.mark.asyncio
async def test_group_provider_failure_still_disconnects_all_instagram_targets_first(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    facebook, linked = _facebook_and_linked_instagram(registry)
    direct = _stage_direct_instagram(registry)
    _force_binding_fields(registry, direct.binding_id, status="active")
    facebook_before = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)

    async def provider_failure(*_args: Any, **_kwargs: Any) -> None:
        raise MetaOAuthError("simulated direct cleanup failure")

    monkeypatch.setattr(graph, "inspect_instagram_login_webhook_subscription", provider_failure)
    targets = bindings_for_disconnect(
        "tenant-a",
        "instagram",
        asset_id=INSTAGRAM_ID,
        registry=registry,
    )
    await disconnect_meta_binding_set(
        targets,
        actor_id="owner",
        registry=registry,
        asset_id=INSTAGRAM_ID,
    )

    rows = {item.binding_id: item for item in registry.list_bindings()}
    assert rows[direct.binding_id].status == "disconnected"
    assert rows[linked.binding_id].status == "disconnected"
    assert registry.binding_credential_is_available(direct.binding_id) is True
    assert registry.binding_credential_is_available(linked.binding_id) is False
    assert rows[facebook.binding_id] == facebook_before
    assert registry.binding_credential_is_available(facebook.binding_id) is True


@pytest.mark.asyncio
async def test_periodic_recovery_finishes_crash_after_group_status_commit(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_instagram_login_lifecycle as lifecycle_module

    facebook, linked = _facebook_and_linked_instagram(registry)
    direct = _stage_direct_instagram(registry)
    _force_binding_fields(registry, direct.binding_id, status="active")
    facebook_before = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)

    targets = bindings_for_disconnect("tenant-a", "instagram", registry=registry)
    registry.disconnect_binding_statuses(
        tuple(item.binding_id for item in targets),
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=None,
        actor_id="owner",
    )

    assert all(
        item.status == "disconnected"
        for item in registry.list_bindings()
        if item.binding_id in {linked.binding_id, direct.binding_id}
    )
    assert registry.binding_credential_is_available(linked.binding_id)
    assert registry.binding_credential_is_available(direct.binding_id)

    provider_calls = _patch_direct_provider_cleanup(monkeypatch)
    monkeypatch.setattr(lifecycle_module, "get_meta_app_registry", lambda: registry)
    result = await lifecycle_module.InstagramLoginLifecycle()._run_cycle(
        actor_id="restart-recovery",
        instagram_configured=False,
    )

    assert result["disconnects_recovered"] == 2
    assert registry.binding_credential_is_available(linked.binding_id) is False
    assert registry.binding_credential_is_available(direct.binding_id) is False
    assert provider_calls == ["inspect", "delete", "inspect"]
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after == facebook_before
    assert registry.binding_credential_is_available(facebook.binding_id) is True
