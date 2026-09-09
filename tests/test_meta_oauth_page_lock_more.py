"""Continuation of Meta OAuth page-lock tests."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from services import meta_oauth_activation
from services.meta_app_registry import APP_A_KEY, MetaCredentialError
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_activation import activate_validated_facebook_pages
from services.meta_subject_deletion_guard import MetaSubjectDeletionChangedError, MetaSubjectDeletionLease
from tests.test_meta_oauth_page_lock import (
    _registry,
    _validated_page,
)


@pytest.mark.asyncio
async def test_cancel_before_graph_write_discards_staged_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    inspecting = asyncio.Event()

    async def inspect(*_args: Any, **_kwargs: Any) -> None:
        inspecting.set()
        await asyncio.Future()

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    task = asyncio.create_task(
        activate_validated_facebook_pages(
            [_validated_page("111222333")],
            tenant_id="linas",
            app_key=APP_A_KEY,
            actor_id="owner",
            registry=registry,
            client=SimpleNamespace(),
        )
    )
    await asyncio.wait_for(inspecting.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)

    rows = registry.list_bindings(include_inactive=True)
    assert len(rows) == 1
    assert rows[0].status == "disconnected"


@pytest.mark.asyncio
async def test_cancel_after_graph_write_shields_restore_and_discard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    write_started = asyncio.Event()
    restore_started = asyncio.Event()
    allow_restore = asyncio.Event()
    restored: list[str] = []

    async def inspect(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def subscribe(binding: Any, **_kwargs: Any) -> None:
        write_started.set()
        await asyncio.Future()

    async def restore(binding: Any, *_args: Any, **_kwargs: Any) -> None:
        restore_started.set()
        await allow_restore.wait()
        restored.append(binding.page_id)

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(meta_oauth_activation, "_restore_binding_webhook_subscription_locked", restore)

    task = asyncio.create_task(
        activate_validated_facebook_pages(
            [_validated_page("444555666")],
            tenant_id="linas",
            app_key=APP_A_KEY,
            actor_id="owner",
            registry=registry,
            client=SimpleNamespace(),
        )
    )
    await asyncio.wait_for(write_started.wait(), timeout=1.0)
    task.cancel()
    await asyncio.wait_for(restore_started.wait(), timeout=1.0)
    task.cancel()
    await asyncio.sleep(0.03)
    assert not task.done()
    allow_restore.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)

    assert restored == ["444555666"]
    rows = registry.list_bindings(include_inactive=True)
    assert len(rows) == 1
    assert rows[0].status == "disconnected"


@pytest.mark.asyncio
async def test_subject_change_after_facebook_provider_write_compensates_and_discards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    provider_writes: list[str] = []
    restored: list[str] = []

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        return ("messages", "messaging_postbacks")

    async def subscribe(binding: Any, **_kwargs: Any) -> None:
        provider_writes.append(binding.page_id)

    async def restore(binding: Any, *_args: Any, **_kwargs: Any) -> None:
        restored.append(binding.page_id)

    def changed(_lease: MetaSubjectDeletionLease) -> None:
        raise MetaSubjectDeletionChangedError("simulated None-to-completed request race")

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(meta_oauth_activation, "_restore_binding_webhook_subscription_locked", restore)
    monkeypatch.setattr(MetaSubjectDeletionLease, "assert_oauth_snapshot_unchanged", changed)

    with pytest.raises(MetaOAuthError, match="deletion state changed"):
        await activate_validated_facebook_pages(
            [_validated_page("777888999")],
            tenant_id="linas",
            app_key=APP_A_KEY,
            actor_id="owner",
            registry=registry,
            client=SimpleNamespace(),
        )

    assert provider_writes == ["777888999"]
    assert restored == ["777888999"]
    rows = registry.list_bindings(include_inactive=True)
    assert len(rows) == 1 and rows[0].status == "disconnected"
    with pytest.raises(MetaCredentialError):
        registry.get_credential(rows[0])


@pytest.mark.asyncio
async def test_facebook_activation_commit_ack_loss_does_not_compensate_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    restored: list[str] = []

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        return ("messages", "messaging_postbacks")

    async def subscribe(binding: Any, **_kwargs: Any) -> None:
        fields = meta_oauth_activation.desired_binding_webhook_subscription(binding, registry=registry)
        with registry._locked():
            state = registry._read_unlocked()
            changed = dict(state["bindings"][binding.binding_id])
            changed["webhook_subscription_status"] = "ready"
            changed["webhook_subscribed_fields"] = list(fields)
            changed["webhook_subscription_checked_at"] = time.time()
            state["bindings"][binding.binding_id] = changed
            registry._write_unlocked(state)

    async def restore(binding: Any, *_args: Any, **_kwargs: Any) -> None:
        restored.append(binding.binding_id)

    real_activate = registry.activate_staged_bindings

    def commit_then_lose_ack(*args: Any, **kwargs: Any) -> None:
        real_activate(*args, **kwargs)
        raise ConnectionError("simulated commit acknowledgement loss")

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(meta_oauth_activation, "_restore_binding_webhook_subscription_locked", restore)
    monkeypatch.setattr(registry, "activate_staged_bindings", commit_then_lose_ack)

    activated = await activate_validated_facebook_pages(
        [_validated_page("555666777")],
        tenant_id="linas",
        app_key=APP_A_KEY,
        actor_id="owner",
        registry=registry,
        client=SimpleNamespace(),
    )

    assert len(activated) == 1 and activated[0].active
    assert activated[0].generation == 2
    assert restored == []


@pytest.mark.asyncio
async def test_facebook_mixed_activation_outcome_is_retained_for_owner_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    restored: list[str] = []

    async def inspect(*_args: Any, **_kwargs: Any) -> tuple[str, ...]:
        return ("messages", "messaging_postbacks")

    async def subscribe(binding: Any, **_kwargs: Any) -> None:
        fields = meta_oauth_activation.desired_binding_webhook_subscription(binding, registry=registry)
        with registry._locked():
            state = registry._read_unlocked()
            changed = dict(state["bindings"][binding.binding_id])
            changed["webhook_subscription_status"] = "ready"
            changed["webhook_subscribed_fields"] = list(fields)
            changed["webhook_subscription_checked_at"] = time.time()
            state["bindings"][binding.binding_id] = changed
            registry._write_unlocked(state)

    async def restore(binding: Any, *_args: Any, **_kwargs: Any) -> None:
        restored.append(binding.binding_id)

    def partial_commit(
        binding_ids: tuple[str, ...],
        *,
        actor_id: str,
        expected_generations: dict[str, int],
        replace_existing: bool,
    ) -> None:
        registry.activate_staged_binding(
            binding_ids[0],
            actor_id=actor_id,
            expected_generation=expected_generations[binding_ids[0]],
            replace_existing=replace_existing,
        )
        raise ConnectionError("simulated impossible partial registry outcome")

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(meta_oauth_activation, "_restore_binding_webhook_subscription_locked", restore)
    monkeypatch.setattr(registry, "activate_staged_bindings", partial_commit)

    with pytest.raises(MetaOAuthError, match="mixed"):
        await activate_validated_facebook_pages(
            [_validated_page("111000111"), _validated_page("222000222")],
            tenant_id="linas",
            app_key=APP_A_KEY,
            actor_id="owner",
            registry=registry,
            client=SimpleNamespace(),
        )

    rows = registry.list_bindings(include_inactive=True, include_superseded=True)
    assert {row.status for row in rows} == {"active", "testing"}
    assert restored == []
