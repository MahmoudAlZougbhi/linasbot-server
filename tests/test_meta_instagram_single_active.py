"""Instagram asset ownership and channel-scoped disconnect regressions."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import httpx
import pytest
from starlette.requests import Request

from modules import meta_connections_api
from services.dashboard_session_service import SessionRecord
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaRegistryError,
    binding_asset_key,
    binding_exclusive_asset_key,
    get_meta_registry_readiness,
)
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.meta_instagram_login_subscription import ensure_instagram_login_webhook_subscription
from services.meta_oauth import MetaOAuthError
from services.mobile_integrations_display import bindings_for_disconnect

pytest_plugins = ("tests.meta_app_registry_fixtures",)

PAGE_ID = "445566778899"
INSTAGRAM_ID = "17840000999900001"


def _credential(*, token: str, auth_flow: str, profile_id: str) -> MetaBindingCredential:
    scopes = (
        (
            "instagram_business_basic",
            "instagram_business_manage_messages",
            "instagram_business_manage_comments",
        )
        if auth_flow == "instagram_login"
        else (
            "pages_show_list",
            "pages_manage_metadata",
            "pages_read_engagement",
            "pages_messaging",
            "instagram_basic",
            "instagram_manage_messages",
        )
    )
    return MetaBindingCredential(
        access_token=token,
        token_app_id="1035856539045307" if auth_flow == "instagram_login" else "2963733803971681",
        token_profile_id=profile_id,
        scopes=scopes,
        expires_at=int(time.time()) + 3600,
        authorized_meta_user_id="9988776655",
        auth_flow=auth_flow,  # type: ignore[arg-type]
    )


def _facebook_and_linked_instagram(registry: MetaAppRegistry) -> tuple[Any, Any]:
    facebook = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="facebook-page-token", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        page_name="Clinic Page",
        auth_flow="facebook_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
    )
    linked = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="page-linked-ig-token", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        instagram_username="clinic_linked",
        auth_flow="facebook_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks", "feed"),
    )
    return facebook, linked


def _stage_direct_instagram(
    registry: MetaAppRegistry,
    *,
    tenant_id: str = "tenant-a",
    webhook_subscription_status: str = "ready",
    webhook_subscribed_fields: tuple[str, ...] = ("messages", "messaging_postbacks", "comments"),
) -> Any:
    return registry.authorize_oauth_asset(
        tenant_id=tenant_id,
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(
            token=f"direct-ig-token-{tenant_id}",
            auth_flow="instagram_login",
            profile_id=INSTAGRAM_ID,
        ),
        actor_id="owner",
        instagram_username="clinic_direct",
        status="testing",
        auth_flow="instagram_login",
        webhook_subscription_status=webhook_subscription_status,
        webhook_subscribed_fields=webhook_subscribed_fields,
        create_new_binding=True,
    )


def _activate_direct(registry: MetaAppRegistry) -> tuple[Any, Any, Any]:
    facebook, linked = _facebook_and_linked_instagram(registry)
    staged = _stage_direct_instagram(registry)
    direct = registry.activate_staged_binding(
        staged.binding_id,
        actor_id="owner",
        expected_generation=staged.generation,
        replace_existing=True,
    )
    registry.archive_superseded_duplicate_bindings(actor_id="owner")
    return facebook, linked, direct


def _force_binding_fields(registry: MetaAppRegistry, binding_id: str, **fields: Any) -> None:
    with registry._locked():
        state = registry._read_unlocked()
        raw = dict(state["bindings"][binding_id])
        raw.update(fields)
        state["bindings"][binding_id] = raw
        registry._write_unlocked(state)


def _request(tenant_id: str = "tenant-a") -> Request:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/meta/connections",
            "query_string": b"",
            "headers": [],
        }
    )
    request.state.dashboard_session = SessionRecord(
        session_id="session-a",
        user_id="owner-a",
        email="owner@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
        csrf_token="csrf",
        created_at=time.time(),
        expires_at=time.time() + 3600,
    )
    return request


def _patch_route_registry(monkeypatch: pytest.MonkeyPatch, registry: MetaAppRegistry) -> None:
    monkeypatch.setattr("modules.meta_connections_api_helpers.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("modules.meta_connections_api_lifecycle.get_meta_app_registry", lambda: registry)


def _patch_direct_provider_cleanup(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    present = True

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...] | None:
        calls.append("inspect")
        return ("comments", "messages", "messaging_postbacks") if present else None

    async def delete(*_args: Any, **_kwargs: Any) -> None:
        nonlocal present
        calls.append("delete")
        present = False

    monkeypatch.setattr("services.meta_oauth_graph.inspect_instagram_login_webhook_subscription", inspect)
    monkeypatch.setattr("services.meta_oauth_graph.unsubscribe_instagram_login_webhook_raw", delete)
    return calls


def test_history_key_stays_flow_specific_but_active_key_does_not() -> None:
    linked_key = binding_asset_key("tenant-a", APP_A_KEY, "instagram", INSTAGRAM_ID, "facebook_login")
    direct_key = binding_asset_key("tenant-a", APP_A_KEY, "instagram", INSTAGRAM_ID, "instagram_login")

    assert linked_key != direct_key
    assert binding_exclusive_asset_key("instagram", INSTAGRAM_ID) == f"instagram:{INSTAGRAM_ID}"


def test_file_registry_repairs_same_tenant_cross_flow_duplicate(registry: MetaAppRegistry) -> None:
    _facebook, linked = _facebook_and_linked_instagram(registry)
    direct = _stage_direct_instagram(registry)
    _force_binding_fields(registry, direct.binding_id, status="active")

    ready_before, checks_before = get_meta_registry_readiness(registry)
    assert ready_before is True
    assert checks_before["registry_backend_ready"] is True
    assert "active_indexes_exclusive" not in checks_before
    duplicate_active = [
        item for item in registry.list_bindings(include_inactive=False) if item.channel == "instagram"
    ]
    assert len(duplicate_active) == 2

    assert registry.archive_superseded_duplicate_bindings(actor_id="repair") == 1
    rows = {item.binding_id: item for item in registry.list_bindings()}
    assert rows[direct.binding_id].status == "active"
    assert rows[direct.binding_id].superseded_by_binding_id == ""
    assert rows[linked.binding_id].status == "inactive"
    assert rows[linked.binding_id].superseded_by_binding_id == direct.binding_id
    active_ig = [item for item in rows.values() if item.channel == "instagram" and item.active]
    assert [item.binding_id for item in active_ig] == [direct.binding_id]


@pytest.mark.parametrize(
    ("subscription_status", "subscribed_fields"),
    [
        ("partial", ("messages", "messaging_postbacks", "comments")),
        ("ready", ("messages", "messaging_postbacks")),
    ],
)
def test_file_registry_keeps_linked_fallback_when_direct_is_not_product_ready(
    registry: MetaAppRegistry,
    subscription_status: str,
    subscribed_fields: tuple[str, ...],
) -> None:
    _facebook, linked = _facebook_and_linked_instagram(registry)
    direct = _stage_direct_instagram(
        registry,
        webhook_subscription_status=subscription_status,
        webhook_subscribed_fields=subscribed_fields,
    )
    _force_binding_fields(registry, direct.binding_id, status="active")
    direct = next(item for item in registry.list_bindings() if item.binding_id == direct.binding_id)

    # DM readiness keeps its existing public meaning; replacement readiness is stricter.
    assert direct.instagram_login_ready is True
    assert direct.instagram_login_product_ready is False

    assert registry.archive_superseded_duplicate_bindings(actor_id="repair") == 1
    rows = {item.binding_id: item for item in registry.list_bindings()}
    assert rows[linked.binding_id].status == "active"
    assert rows[linked.binding_id].superseded_by_binding_id == ""
    assert rows[direct.binding_id].status == "inactive"
    assert rows[direct.binding_id].superseded_by_binding_id == linked.binding_id


def test_file_registry_unhides_single_active_keeper(registry: MetaAppRegistry) -> None:
    direct = _stage_direct_instagram(registry)
    _force_binding_fields(
        registry,
        direct.binding_id,
        status="active",
        superseded_by_binding_id="stale-keeper",
    )
    before = next(item for item in registry.list_bindings() if item.binding_id == direct.binding_id)

    assert registry.archive_superseded_duplicate_bindings(actor_id="repair") == 1

    after = next(item for item in registry.list_bindings() if item.binding_id == direct.binding_id)
    assert after.status == "active"
    assert after.superseded_by_binding_id == ""
    assert after.generation == before.generation + 1
    assert after.updated_at >= before.updated_at


def test_file_registry_cross_tenant_duplicate_fails_closed_without_mutation(
    registry: MetaAppRegistry,
) -> None:
    _facebook, linked = _facebook_and_linked_instagram(registry)
    direct = _stage_direct_instagram(registry)
    _force_binding_fields(
        registry,
        direct.binding_id,
        tenant_id="tenant-b",
        status="active",
        superseded_by_binding_id=linked.binding_id,
    )
    before = json.loads(registry.store_path.read_text(encoding="utf-8"))

    with pytest.raises(MetaBindingConflictError, match="multiple workspaces"):
        registry.archive_superseded_duplicate_bindings(actor_id="repair")

    after = json.loads(registry.store_path.read_text(encoding="utf-8"))
    assert after == before


def test_activation_preflight_cannot_name_cross_tenant_owner_as_replacement(
    registry: MetaAppRegistry,
) -> None:
    _facebook, linked = _facebook_and_linked_instagram(registry)
    staged = _stage_direct_instagram(registry)
    _force_binding_fields(registry, linked.binding_id, tenant_id="tenant-b")

    with pytest.raises(MetaBindingConflictError, match="ownership boundary"):
        registry.assert_binding_can_activate(
            staged.binding_id,
            expected_generation=staged.generation,
            replacing_binding_id=linked.binding_id,
        )


def test_concurrent_cross_flow_activation_keeps_exactly_one_active(registry: MetaAppRegistry) -> None:
    linked = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="linked-stage", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        status="testing",
        auth_flow="facebook_login",
        create_new_binding=True,
    )
    direct = _stage_direct_instagram(registry)
    barrier = threading.Barrier(2)

    def activate(binding: Any) -> str:
        barrier.wait(timeout=5)
        try:
            registry.activate_staged_binding(
                binding.binding_id,
                actor_id="owner",
                expected_generation=binding.generation,
                replace_existing=False,
            )
            return "active"
        except MetaBindingConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(activate, (linked, direct)))

    assert sorted(results) == ["active", "conflict"]
    active = [
        item
        for item in registry.list_bindings(include_inactive=False)
        if item.channel == "instagram" and item.asset_id == INSTAGRAM_ID
    ]
    assert len(active) == 1


def test_registry_transaction_depth_is_never_inherited_by_another_thread(
    registry: MetaAppRegistry,
) -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def hold_first_transaction() -> None:
        with registry._locked():
            first_entered.set()
            assert release_first.wait(timeout=2)

    def enter_second_transaction() -> None:
        assert first_entered.wait(timeout=2)
        with registry._locked():
            second_entered.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(hold_first_transaction)
        assert first_entered.wait(timeout=2)
        second = pool.submit(enter_second_transaction)
        time.sleep(0.05)
        assert second_entered.is_set() is False
        release_first.set()
        first.result(timeout=2)
        second.result(timeout=2)

    assert second_entered.is_set()


def test_direct_active_authorization_cannot_bypass_staged_cross_flow_cutover(
    registry: MetaAppRegistry,
) -> None:
    _facebook, _linked = _facebook_and_linked_instagram(registry)

    with pytest.raises(MetaBindingConflictError, match="another active binding"):
        registry.authorize_oauth_asset(
            tenant_id="tenant-a",
            channel="instagram",
            asset_id=INSTAGRAM_ID,
            page_id="",
            instagram_account_id=INSTAGRAM_ID,
            app_key=APP_A_KEY,
            credential=_credential(
                token="direct-bypass-token",
                auth_flow="instagram_login",
                profile_id=INSTAGRAM_ID,
            ),
            actor_id="owner",
            status="active",
            auth_flow="instagram_login",
            webhook_subscription_status="ready",
            webhook_subscribed_fields=("messages", "messaging_postbacks"),
        )


def test_facebook_page_set_activation_supersedes_direct_ig_without_two_active_rows(
    registry: MetaAppRegistry,
) -> None:
    direct = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id="",
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(
            token="working-direct-token",
            auth_flow="instagram_login",
            profile_id=INSTAGRAM_ID,
        ),
        actor_id="owner",
        status="active",
        auth_flow="instagram_login",
        webhook_subscription_status="ready",
        webhook_subscribed_fields=("messages", "messaging_postbacks"),
    )
    staged_facebook = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="fresh-page-token", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        status="testing",
        auth_flow="facebook_login",
        create_new_binding=True,
    )
    staged_linked = registry.authorize_oauth_asset(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id=INSTAGRAM_ID,
        page_id=PAGE_ID,
        instagram_account_id=INSTAGRAM_ID,
        app_key=APP_A_KEY,
        credential=_credential(token="fresh-linked-token", auth_flow="facebook_login", profile_id=PAGE_ID),
        actor_id="owner",
        status="testing",
        auth_flow="facebook_login",
        create_new_binding=True,
    )

    activated = registry.activate_staged_bindings(
        (staged_facebook.binding_id, staged_linked.binding_id),
        actor_id="owner",
        expected_generations={
            staged_facebook.binding_id: staged_facebook.generation,
            staged_linked.binding_id: staged_linked.generation,
        },
        replace_existing=True,
    )

    assert {item.channel for item in activated} == {"facebook", "instagram"}
    rows = {item.binding_id: item for item in registry.list_bindings()}
    assert rows[direct.binding_id].status == "inactive"
    assert rows[direct.binding_id].superseded_by_binding_id == staged_linked.binding_id
    active_ig = [
        item for item in rows.values() if item.channel == "instagram" and item.asset_id == INSTAGRAM_ID and item.active
    ]
    assert [item.binding_id for item in active_ig] == [staged_linked.binding_id]


@pytest.mark.asyncio
async def test_instagram_disconnect_settles_both_flows_and_preserves_facebook(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_calls = _patch_direct_provider_cleanup(monkeypatch)
    facebook, linked, direct = _activate_direct(registry)
    facebook_before = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    facebook_token = registry.get_credential(facebook_before).access_token

    targets = bindings_for_disconnect(
        "tenant-a",
        "instagram",
        asset_id=INSTAGRAM_ID,
        registry=registry,
    )
    disconnected = await disconnect_meta_binding_set(
        targets,
        actor_id="owner",
        registry=registry,
        asset_id=INSTAGRAM_ID,
    )

    assert {item.binding_id for item in disconnected} == {linked.binding_id, direct.binding_id}
    assert all(item.status == "disconnected" for item in disconnected)
    assert all(not registry.binding_credential_is_available(item.binding_id) for item in disconnected)
    facebook_after = next(item for item in registry.list_bindings() if item.binding_id == facebook.binding_id)
    assert facebook_after.status == "active"
    assert facebook_after.webhook_subscribed_fields == facebook_before.webhook_subscribed_fields
    assert registry.get_credential(facebook_after).access_token == facebook_token
    assert provider_calls == ["inspect", "delete", "inspect"]


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
        assert request.url.path == f"/v24.0/{INSTAGRAM_ID}/subscribed_apps"
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
