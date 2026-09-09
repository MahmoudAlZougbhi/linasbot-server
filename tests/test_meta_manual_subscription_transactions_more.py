"""Regression tests for manual Meta Page subscription lifecycle transactions."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

import httpx
import pytest

from modules import meta_connections_api_lifecycle as lifecycle
from services.meta_app_registry import (
    APP_A_KEY,
    APP_B_KEY,
    MetaAppRegistry,
    MetaBindingCredential,
    MetaRegistryError,
)
from services.meta_oauth_graph import MetaOAuthError

PAGE_ID = "112233445566"
APP_A_ID = "2963733803971681"
APP_B_ID = "998877665544"
SCOPES = (
    "pages_show_list",
    "pages_manage_metadata",
    "pages_read_engagement",
    "pages_messaging",
    "instagram_basic",
    "instagram_manage_messages",
)
DESIRED = ("messages", "messaging_postbacks")


@pytest.fixture
def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    monkeypatch.setenv("META_APP_A_ID", APP_A_ID)
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_APP_B_ID", APP_B_ID)
    monkeypatch.setenv("META_APP_B_SECRET", "app-b-secret-tests")
    monkeypatch.setenv("META_APP_B_WEBHOOK_VERIFY_TOKEN", "verify-b-tests")
    monkeypatch.setenv("META_APP_B_ADVANCED_ACCESS_APPROVED", "true")
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="manual-page-transaction-tests-secret-123456789",
    )


def _credential(app_id: str, token: str) -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token=token,
        token_app_id=app_id,
        token_profile_id=PAGE_ID,
        scopes=SCOPES,
        expires_at=int(time.time()) + 3600,
    )


def _staged_b_then_active_a(registry: MetaAppRegistry) -> tuple[Any, Any]:
    staged = registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        instagram_account_id="",
        app_key=APP_B_KEY,
        credential=_credential(APP_B_ID, "private-app-b-page-token"),
        actor_id="owner",
        status="testing",
    )
    old = registry.activate_binding(
        tenant_id="tenant-a",
        channel="facebook",
        asset_id=PAGE_ID,
        page_id=PAGE_ID,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(APP_A_ID, "private-app-a-page-token"),
        actor_id="owner",
    )
    return staged, old


def _binding(registry: MetaAppRegistry, binding_id: str) -> Any:
    return next(item for item in registry.list_bindings() if item.binding_id == binding_id)


def _record_ready_subscription(registry: MetaAppRegistry, binding: Any, fields: tuple[str, ...]) -> None:
    with registry._locked():
        state = registry._read_unlocked()
        changed = dict(state["bindings"][binding.binding_id])
        changed["webhook_subscription_status"] = "ready"
        changed["webhook_subscribed_fields"] = list(fields)
        changed["webhook_subscription_checked_at"] = time.time()
        state["bindings"][binding.binding_id] = changed
        registry._write_unlocked(state)


@pytest.mark.asyncio
async def test_manual_activate_and_rollback_preserve_third_shared_bindings(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    staged, old = _staged_b_then_active_a(registry)
    third_a = registry.activate_binding(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id="17840000000000001",
        page_id=PAGE_ID,
        instagram_account_id="17840000000000001",
        app_key=APP_A_KEY,
        credential=_credential(APP_A_ID, "private-third-app-a-token"),
        actor_id="owner",
    )
    third_b = registry.activate_binding(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id="17840000000000002",
        page_id=PAGE_ID,
        instagram_account_id="17840000000000002",
        app_key=APP_B_KEY,
        credential=_credential(APP_B_ID, "private-third-app-b-token"),
        actor_id="owner",
    )

    async def inspect(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def subscribe(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def unexpected_delete(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("an active third binding still owns this app/Page provider row")

    monkeypatch.setattr("modules.meta_connections_api_helpers.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr(
        "services.meta_page_subscription_transaction.inspect_binding_webhook_subscription",
        inspect,
    )
    monkeypatch.setattr(lifecycle, "desired_binding_webhook_subscription", lambda *_args, **_kwargs: DESIRED)
    monkeypatch.setattr(lifecycle, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(lifecycle, "_unsubscribe_binding_webhook_locked_raw", unexpected_delete)

    activated = await lifecycle._activate_meta_connection_locked(staged, old, actor_id="owner", registry=registry)
    previous = _binding(registry, old.binding_id)
    restored = await lifecycle._rollback_meta_connection_locked(
        activated,
        previous,
        actor_id="owner",
        registry=registry,
    )

    assert restored.binding_id == old.binding_id
    assert _binding(registry, third_a.binding_id).active
    assert _binding(registry, third_b.binding_id).active


@pytest.mark.asyncio
async def test_public_unsubscribe_refuses_to_delete_a_shared_app_page(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    _staged, binding = _staged_b_then_active_a(registry)
    registry.activate_binding(
        tenant_id="tenant-a",
        channel="instagram",
        asset_id="17840000000000003",
        page_id=PAGE_ID,
        instagram_account_id="17840000000000003",
        app_key=APP_A_KEY,
        credential=_credential(APP_A_ID, "private-shared-app-a-token"),
        actor_id="owner",
    )

    async def unexpected_delete(*_args: Any, **_kwargs: Any) -> None:
        pytest.fail("public unsubscribe must fail safe when another binding is active")

    monkeypatch.setattr(graph, "_unsubscribe_binding_webhook_locked_raw", unexpected_delete)

    assert await graph.unsubscribe_binding_webhook(binding, registry=registry) is False


@pytest.mark.asyncio
async def test_disconnect_cancellation_after_delete_settles_local_disconnect(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    _staged, binding = _staged_b_then_active_a(registry)

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        return DESIRED

    async def cancel_after_delete(*_args: Any, **_kwargs: Any) -> None:
        task = asyncio.current_task()
        assert task is not None
        task.cancel()
        await asyncio.sleep(0)

    monkeypatch.setattr(graph, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(graph, "_unsubscribe_binding_webhook_locked_raw", cancel_after_delete)

    with pytest.raises(asyncio.CancelledError):
        await graph.disconnect_binding_webhook(
            binding,
            actor_id="owner",
            registry=registry,
        )

    disconnected = _binding(registry, binding.binding_id)
    assert disconnected.status == "disconnected"
    assert registry.get_credential(disconnected).access_token


@pytest.mark.asyncio
async def test_disconnect_local_cas_failure_does_not_mutate_provider(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import services.meta_oauth_graph as graph

    _staged, binding = _staged_b_then_active_a(registry)
    events: list[str] = []

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        events.append("inspect")
        return DESIRED

    async def deleted(*_args: Any, **_kwargs: Any) -> None:
        events.append("delete")
        return None

    async def local_failure(*_args: Any, **_kwargs: Any) -> None:
        events.append("local")
        raise MetaRegistryError("simulated disconnect CAS")

    monkeypatch.setattr(graph, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(graph, "_unsubscribe_binding_webhook_locked_raw", deleted)
    monkeypatch.setattr(graph, "_settle_binding_disconnect", local_failure)

    with pytest.raises(MetaRegistryError, match="disconnect CAS"):
        await graph.disconnect_binding_webhook(
            binding,
            actor_id="owner",
            registry=registry,
        )

    assert events == ["local"]
    assert _binding(registry, binding.binding_id).active


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_success", [False, True])
async def test_page_disconnect_keeps_credential_until_delete_absence_is_verified(
    registry: MetaAppRegistry,
    delete_success: bool,
) -> None:
    import services.meta_oauth_graph as graph

    _staged, binding = _staged_b_then_active_a(registry)
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.method)
        if request.method == "DELETE":
            return httpx.Response(200, json={"success": delete_success})
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": APP_A_ID,
                        "subscribed_fields": list(DESIRED),
                    }
                ]
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://graph.facebook.com/v24.0",
    ) as client:
        with pytest.raises(MetaOAuthError, match="disconnect"):
            await graph.disconnect_binding_webhook(
                binding,
                actor_id="owner",
                registry=registry,
                client=client,
            )

    latest = _binding(registry, binding.binding_id)
    assert latest.status == "disconnected"
    assert registry.binding_credential_is_available(latest.binding_id) is True
    assert calls == ["GET", "DELETE", "GET"]


@pytest.mark.asyncio
async def test_page_disconnect_accepts_lost_delete_ack_only_after_absence_readback(
    registry: MetaAppRegistry,
) -> None:
    import services.meta_oauth_graph as graph

    _staged, binding = _staged_b_then_active_a(registry)
    present = True
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal present
        calls.append(request.method)
        if request.method == "DELETE":
            present = False
            raise httpx.ReadError("simulated lost DELETE acknowledgement", request=request)
        rows = [{"id": APP_A_ID, "subscribed_fields": list(DESIRED)}] if present else []
        return httpx.Response(200, json={"data": rows})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://graph.facebook.com/v24.0",
    ) as client:
        settled = await graph.disconnect_binding_webhook(
            binding,
            actor_id="owner",
            registry=registry,
            client=client,
        )

    assert settled.status == "disconnected"
    assert registry.binding_credential_is_available(binding.binding_id) is False
    assert calls == ["GET", "DELETE", "GET"]


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_method", ["set_binding_status", "archive_binding_credential"])
async def test_page_disconnect_reconciles_local_commit_ack_loss_in_same_call(
    registry: MetaAppRegistry,
    monkeypatch: pytest.MonkeyPatch,
    commit_method: str,
) -> None:
    import services.meta_oauth_graph as graph

    _staged, binding = _staged_b_then_active_a(registry)
    original = getattr(registry, commit_method)
    failed_once = False

    def commit_then_throw(*args: object, **kwargs: object) -> object:
        nonlocal failed_once
        committed = original(*args, **kwargs)
        if not failed_once:
            failed_once = True
            raise MetaRegistryError(f"simulated {commit_method} acknowledgement loss")
        return committed

    monkeypatch.setattr(registry, commit_method, commit_then_throw)
    present = True
    calls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal present
        calls.append(request.method)
        if request.method == "DELETE":
            present = False
            return httpx.Response(200, json={"success": True})
        rows = [{"id": APP_A_ID, "subscribed_fields": list(DESIRED)}] if present else []
        return httpx.Response(200, json={"data": rows})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://graph.facebook.com/v24.0",
    ) as client:
        settled = await graph.disconnect_binding_webhook(
            binding,
            actor_id="owner",
            registry=registry,
            client=client,
        )

    assert settled.status == "disconnected"
    assert registry.binding_credential_is_available(binding.binding_id) is False
    assert calls == ["GET", "DELETE", "GET"]
