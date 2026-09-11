"""Instagram asset ownership and cross-flow activation tests."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from services.meta_app_registry import (
    APP_A_KEY,
    MetaAppRegistry,
    MetaBindingConflictError,
    binding_asset_key,
    binding_exclusive_asset_key,
    get_meta_registry_readiness,
)
from services.meta_connection_disconnect import disconnect_meta_binding_set
from services.mobile_integrations_display import bindings_for_disconnect
from tests.meta_instagram_single_active_support import (
    INSTAGRAM_ID,
    PAGE_ID,
    _activate_direct,
    _credential,
    _facebook_and_linked_instagram,
    _force_binding_fields,
    _patch_direct_provider_cleanup,
    _stage_direct_instagram,
)

pytest_plugins = ("tests.meta_instagram_single_active_support", "tests.meta_app_registry_fixtures")


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
    duplicate_active = [item for item in registry.list_bindings(include_inactive=False) if item.channel == "instagram"]
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
