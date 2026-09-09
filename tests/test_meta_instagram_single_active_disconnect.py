"""Instagram channel-scoped disconnect and retry tests."""

from __future__ import annotations

from typing import Any

import pytest

from modules import meta_connections_api
from services.meta_app_registry import (
    MetaAppRegistry,
    MetaRegistryError,
)
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.mobile_integrations_display import bindings_for_disconnect
from tests.meta_instagram_single_active_support import (
    INSTAGRAM_ID,
    _activate_direct,
    _facebook_and_linked_instagram,
    _patch_direct_provider_cleanup,
    _patch_route_registry,
    _request,
    _stage_direct_instagram,
)

pytest_plugins = ('tests.meta_instagram_single_active_support', 'tests.meta_app_registry_fixtures')

@pytest.mark.asyncio
async def test_instagram_disconnect_then_reconnect_converges_to_one_fresh_binding(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_provider_cleanup(monkeypatch)
    facebook, linked, direct = _activate_direct(registry)
    targets = bindings_for_disconnect("tenant-a", "instagram", registry=registry)
    await disconnect_meta_binding_set(targets, actor_id="owner", registry=registry)

    staged = _stage_direct_instagram(registry)
    reconnected = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
        replace_existing=False,
    )
    registry.archive_superseded_duplicate_bindings(actor_id="owner")

    active_ig = [
        item
        for item in registry.list_bindings(include_inactive=False)
        if item.tenant_id == "tenant-a" and item.channel == "instagram"
    ]
    assert [item.binding_id for item in active_ig] == [reconnected.binding_id]
    assert registry.binding_credential_is_available(reconnected.binding_id) is True
    assert registry.binding_credential_is_available(linked.binding_id) is False
    assert registry.binding_credential_is_available(direct.binding_id) is False
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after.active
    assert registry.binding_credential_is_available(facebook.binding_id) is True


@pytest.mark.asyncio
async def test_instagram_route_clears_only_instagram_toggles(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_direct_provider_cleanup(monkeypatch)
    facebook, _linked, direct = _activate_direct(registry)
    _patch_route_registry(monkeypatch, registry)
    cleared: list[str] = []

    async def clear_toggles(**kwargs: Any) -> bool:
        cleared.append(str(kwargs["platform"]))
        return True

    monkeypatch.setattr(
        "services.channel_capability_disconnect.clear_channel_toggles_after_disconnect",
        clear_toggles,
    )
    response = await meta_connections_api.disconnect_meta_connection(direct.binding_id, _request())

    assert response["success"] is True
    assert cleared == ["instagram"]
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after.status == "active"
    assert registry.binding_credential_is_available(facebook_after.binding_id) is True


@pytest.mark.asyncio
async def test_linked_instagram_disconnect_never_unsubscribes_active_facebook_page(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facebook, linked = _facebook_and_linked_instagram(registry)
    _patch_route_registry(monkeypatch, registry)
    facebook_before = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    facebook_token = registry.get_credential(facebook_before).access_token
    provider_calls: list[str] = []
    cleared: list[str] = []

    async def unexpected_provider_call(*_args: Any, **_kwargs: Any) -> Any:
        provider_calls.append("unsubscribe")
        raise AssertionError("Facebook Page subscription must remain installed")

    async def clear_toggles(**kwargs: Any) -> bool:
        cleared.append(str(kwargs["platform"]))
        return True

    monkeypatch.setattr(
        "services.meta_oauth_graph.inspect_binding_webhook_subscription",
        unexpected_provider_call,
    )
    monkeypatch.setattr(
        "services.meta_oauth_graph._unsubscribe_binding_webhook_locked_raw",
        unexpected_provider_call,
    )
    monkeypatch.setattr(
        "services.channel_capability_disconnect.clear_channel_toggles_after_disconnect",
        clear_toggles,
    )

    response = await meta_connections_api.disconnect_meta_connection(linked.binding_id, _request())

    assert response["success"] is True
    assert provider_calls == []
    assert cleared == ["instagram"]
    linked_after = next(item for item in registry.list_bindings() if item.binding_id == linked.binding_id)
    assert linked_after.status == "disconnected"
    assert registry.binding_credential_is_available(linked.binding_id) is False
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after == facebook_before
    assert registry.get_credential(facebook_after).access_token == facebook_token


@pytest.mark.asyncio
async def test_facebook_route_leaves_both_instagram_histories_untouched(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facebook, linked, direct = _activate_direct(registry)
    _patch_route_registry(monkeypatch, registry)
    ig_before = {item.binding_id: item for item in registry.list_bindings() if item.channel == "instagram"}
    cleared: list[str] = []

    async def settle_without_graph(binding: Any, *, actor_id: str, registry: MetaAppRegistry) -> Any:
        changed = registry.set_binding_status(
            binding.binding_id,
            status="disconnected",
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
        return registry.archive_binding_credential(
            changed.binding_id,
            actor_id=actor_id,
            expected_generation=changed.generation,
        )

    async def clear_toggles(**kwargs: Any) -> bool:
        cleared.append(str(kwargs["platform"]))
        return True

    monkeypatch.setattr(
        "services.meta_connection_disconnect.disconnect_binding_webhook",
        settle_without_graph,
    )
    monkeypatch.setattr(
        "services.channel_capability_disconnect.clear_channel_toggles_after_disconnect",
        clear_toggles,
    )
    response = await meta_connections_api.disconnect_meta_connection(facebook.binding_id, _request())

    assert response["success"] is True
    assert cleared == ["facebook"]
    ig_after = {item.binding_id: item for item in registry.list_bindings() if item.channel == "instagram"}
    assert ig_after == ig_before
    assert registry.binding_credential_is_available(direct.binding_id) is True
    assert registry.binding_credential_is_available(linked.binding_id) is True


@pytest.mark.asyncio
async def test_disconnect_retry_archives_commit_then_throw_credential(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facebook, linked, direct = _activate_direct(registry)
    failed_once = False

    async def commit_then_throw(binding: Any, *, actor_id: str, registry: MetaAppRegistry) -> Any:
        nonlocal failed_once
        changed = registry.set_binding_status(
            binding.binding_id,
            status="disconnected",
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
        if not failed_once:
            failed_once = True
            raise MetaRegistryError("simulated commit acknowledgement failure")
        return registry.archive_binding_credential(
            changed.binding_id,
            actor_id=actor_id,
            expected_generation=changed.generation,
        )

    monkeypatch.setattr(
        "services.meta_connection_disconnect.disconnect_binding_webhook",
        commit_then_throw,
    )
    targets = bindings_for_disconnect("tenant-a", "instagram", registry=registry)
    await disconnect_meta_binding_set(targets, actor_id="owner", registry=registry)

    pending_ids = {
        item.binding_id for item in (linked, direct) if registry.binding_credential_is_available(item.binding_id)
    }
    assert len(pending_ids) == 1
    retry_targets = bindings_for_disconnect("tenant-a", "instagram", registry=registry)
    assert {item.binding_id for item in retry_targets} == pending_ids
    await disconnect_meta_binding_set(retry_targets, actor_id="owner", registry=registry)

    assert registry.binding_credential_is_available(direct.binding_id) is False
    assert registry.binding_credential_is_available(linked.binding_id) is False
    assert next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id).active


@pytest.mark.asyncio
async def test_disconnect_postcondition_detects_new_hidden_sibling_then_retry_settles_it(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _facebook, _linked, direct = _activate_direct(registry)
    injected: Any | None = None

    async def settle_and_inject(binding: Any, *, actor_id: str, registry: MetaAppRegistry) -> Any:
        nonlocal injected
        changed = registry.set_binding_status(
            binding.binding_id,
            status="disconnected",
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
        changed = registry.archive_binding_credential(
            changed.binding_id,
            actor_id=actor_id,
            expected_generation=changed.generation,
        )
        if injected is None:
            injected = _stage_direct_instagram(registry)
        return changed

    monkeypatch.setattr(
        "services.meta_connection_disconnect.disconnect_binding_webhook",
        settle_and_inject,
    )
    targets = bindings_for_disconnect(
        "tenant-a",
        "instagram",
        asset_id=INSTAGRAM_ID,
        registry=registry,
    )
    with pytest.raises(MetaRegistryError, match="scope changed"):
        await disconnect_meta_binding_set(
            targets,
            actor_id="owner",
            registry=registry,
            asset_id=INSTAGRAM_ID,
        )

    retry_targets = bindings_for_disconnect(
        "tenant-a",
        "instagram",
        asset_id=INSTAGRAM_ID,
        registry=registry,
    )
    await disconnect_meta_binding_set(
        retry_targets,
        actor_id="owner",
        registry=registry,
        asset_id=INSTAGRAM_ID,
    )
    assert injected is not None
    assert registry.binding_credential_is_available(injected.binding_id) is False
    assert not [
        item
        for item in registry.list_bindings()
        if item.tenant_id == "tenant-a"
        and item.channel == "instagram"
        and item.asset_id == INSTAGRAM_ID
        and item.status != "disconnected"
    ]
