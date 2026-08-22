from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from services import meta_oauth_activation, meta_oauth_page_lock
from services.meta_app_registry import APP_A_KEY, MetaAppRegistry, MetaBindingCredential, MetaCredentialError
from services.meta_comment_webhooks import ensure_page_comment_webhook_subscription
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_activation import ValidatedFacebookPage, activate_validated_facebook_pages
from services.meta_oauth_graph import subscribe_binding_webhook
from services.meta_subject_deletion_guard import MetaSubjectDeletionChangedError, MetaSubjectDeletionLease
from tests.meta_compliance_helpers import _FakeFirestore


def _file_registry(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(_backend="file", lock_path=str(tmp_path / "registry.lock"))


@pytest.mark.asyncio
async def test_cancelled_local_wait_does_not_leak_process_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meta_oauth_page_lock, "_LOCK_ACQUIRE_TIMEOUT_SECONDS", 1.0)
    name = meta_oauth_page_lock._lock_names(app_key="app_a", page_ids=("123",))[0]
    held = meta_oauth_page_lock._local_lock(name)
    assert held.acquire(blocking=False)

    async def enter_lock() -> None:
        async with meta_oauth_page_lock.lock_facebook_page_oauth_operation(
            _file_registry(tmp_path),
            app_key="app_a",
            page_ids=("123",),
        ):
            raise AssertionError("cancelled waiter must not enter the protected operation")

    waiter = asyncio.create_task(enter_lock())
    await asyncio.sleep(0.02)
    waiter.cancel()
    held.release()
    with pytest.raises(asyncio.CancelledError):
        await waiter

    assert held.acquire(blocking=False), "cancelled to_thread acquisition leaked the local lock"
    held.release()


@pytest.mark.asyncio
async def test_process_lock_contention_fails_with_bounded_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meta_oauth_page_lock, "_LOCK_ACQUIRE_TIMEOUT_SECONDS", 0.05)
    name = meta_oauth_page_lock._lock_names(app_key="app_a", page_ids=("456",))[0]
    held = meta_oauth_page_lock._local_lock(name)
    assert held.acquire(blocking=False)
    try:
        with pytest.raises(meta_oauth_page_lock.MetaOAuthPageLockError, match="process lock timed out"):
            async with meta_oauth_page_lock.lock_facebook_page_oauth_operation(
                _file_registry(tmp_path),
                app_key="app_a",
                page_ids=("456",),
            ):
                raise AssertionError("timed-out waiter must not enter the protected operation")
    finally:
        held.release()


@pytest.mark.asyncio
async def test_multiple_lock_phases_share_one_overall_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(meta_oauth_page_lock, "_LOCK_ACQUIRE_TIMEOUT_SECONDS", 0.2)
    first_name, second_name = meta_oauth_page_lock._lock_names(
        app_key="app_a",
        page_ids=("100", "200"),
    )
    first = meta_oauth_page_lock._local_lock(first_name)
    second = meta_oauth_page_lock._local_lock(second_name)
    assert first.acquire(blocking=False)
    assert second.acquire(blocking=False)

    async def release_first() -> None:
        await asyncio.sleep(0.12)
        first.release()

    releaser = asyncio.create_task(release_first())
    started = time.monotonic()
    try:
        with pytest.raises(meta_oauth_page_lock.MetaOAuthPageLockError, match="process lock timed out"):
            async with meta_oauth_page_lock.lock_facebook_page_oauth_operation(
                _file_registry(tmp_path),
                app_key="app_a",
                page_ids=("100", "200"),
            ):
                raise AssertionError("the second process lock must remain unavailable")
    finally:
        await releaser
        second.release()
    assert time.monotonic() - started < 0.27


@pytest.mark.asyncio
async def test_reentry_is_same_task_only_even_when_child_inherits_context(tmp_path: Path) -> None:
    registry = _file_registry(tmp_path)
    child_entered = asyncio.Event()

    async def child() -> None:
        async with meta_oauth_page_lock.lock_facebook_page_oauth_operation(
            registry,
            app_key="app_b",
            page_ids=("789",),
        ):
            child_entered.set()

    async with meta_oauth_page_lock.lock_facebook_page_oauth_operation(
        registry,
        app_key="app_a",
        page_ids=("789",),
    ):
        # Same-task, cross-app re-entry succeeds because the resource key is Page-wide.
        async with meta_oauth_page_lock.lock_facebook_page_oauth_operation(
            registry,
            app_key="app_b",
            page_ids=("789",),
        ):
            pass
        child_task = asyncio.create_task(child())
        await asyncio.sleep(0.03)
        assert not child_entered.is_set()

    await asyncio.wait_for(child_task, timeout=1.0)
    assert child_entered.is_set()


def test_postgres_lock_engine_is_dedicated_and_connect_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    import sqlalchemy
    from sqlalchemy.pool import NullPool

    from db import session as db_session

    sentinel = object()
    captured: dict[str, Any] = {}

    def create_engine(url: str, **kwargs: Any) -> object:
        captured["url"] = url
        captured.update(kwargs)
        return sentinel

    monkeypatch.setattr(db_session, "database_url", lambda: "postgresql://user:pass@db.example/meta")
    monkeypatch.setattr(db_session, "_normalize_database_url", lambda value: value)
    monkeypatch.setattr(sqlalchemy, "create_engine", create_engine)

    engine = meta_oauth_page_lock._create_dedicated_postgres_engine(deadline=time.monotonic() + 2.0)

    assert engine is sentinel
    assert captured["poolclass"] is NullPool
    assert 1 <= captured["connect_args"]["connect_timeout"] <= 2
    assert str(captured["connect_args"]["options"]).startswith("-c statement_timeout=")


def test_ops_lock_target_loads_database_url_from_root_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            (
                "META_REGISTRY_BACKEND=postgres",
                "LINASBOT_DATA_ROOT=/srv/linas-data",
                "DATABASE_URL=postgresql://user:private-password@db.example/meta",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)

    target = meta_oauth_page_lock.page_lock_target_from_env_file(env_file)

    assert target.backend == "postgres"
    assert target.lock_path == Path("/srv/linas-data/meta_registry/registry.lock")
    assert target.database_url.endswith("@db.example/meta")
    assert "private-password" not in repr(target)


def _registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MetaAppRegistry:
    import utils.utils

    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    monkeypatch.setenv("META_APP_A_ID", "2963733803971681")
    monkeypatch.setenv("META_APP_A_SECRET", "app-a-secret-tests")
    monkeypatch.setenv("META_APP_A_WEBHOOK_VERIFY_TOKEN", "verify-a-tests")
    monkeypatch.setenv("META_GRAPH_API_VERSION", "v24.0")
    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)

    async def _enable_channel_defaults(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "services.channel_capability_toggles.enable_channel_defaults_after_connect",
        _enable_channel_defaults,
    )
    return MetaAppRegistry(
        store_path=tmp_path / "registry.json",
        audit_path=tmp_path / "audit.jsonl",
        master_secret="page-lock-registry-secret-tests-123456789",
    )


def _credential(page_id: str) -> MetaBindingCredential:
    return MetaBindingCredential(
        access_token="page-token-private",
        token_app_id="2963733803971681",
        token_profile_id=page_id,
        scopes=(
            "pages_manage_engagement",
            "pages_manage_metadata",
            "pages_messaging",
            "pages_read_engagement",
            "pages_read_user_content",
            "pages_show_list",
        ),
        authorized_meta_user_id="123456789",
    )


@pytest.mark.asyncio
async def test_oauth_and_comment_writers_cannot_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    page_id = "378696005334409"
    binding = registry.activate_binding(
        tenant_id="linas",
        channel="facebook",
        asset_id=page_id,
        page_id=page_id,
        instagram_account_id="",
        app_key=APP_A_KEY,
        credential=_credential(page_id),
        actor_id="owner",
    )
    first_posted = asyncio.Event()
    release_first = asyncio.Event()
    second_posted = asyncio.Event()
    fields = ["feed", "messages", "messaging_postbacks", "standby"]

    async def first_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            first_posted.set()
            await release_first.wait()
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"data": [{"id": "2963733803971681", "subscribed_fields": fields}]})

    async def second_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            second_posted.set()
            return httpx.Response(200, json={"success": True})
        return httpx.Response(200, json={"data": [{"id": "2963733803971681", "subscribed_fields": fields}]})

    async with (
        httpx.AsyncClient(
            base_url="https://graph.facebook.com/v24.0/",
            transport=httpx.MockTransport(first_handler),
        ) as first_client,
        httpx.AsyncClient(
            base_url="https://graph.facebook.com/v24.0/",
            transport=httpx.MockTransport(second_handler),
        ) as second_client,
    ):
        oauth_writer = asyncio.create_task(subscribe_binding_webhook(binding, registry=registry, client=first_client))
        await asyncio.wait_for(first_posted.wait(), timeout=1.0)
        comment_writer = asyncio.create_task(
            ensure_page_comment_webhook_subscription(binding, registry=registry, client=second_client)
        )
        await asyncio.sleep(0.03)
        assert not second_posted.is_set()
        release_first.set()
        await asyncio.wait_for(oauth_writer, timeout=1.0)
        await asyncio.wait_for(comment_writer, timeout=1.0)

    assert second_posted.is_set()


def _validated_page(page_id: str) -> ValidatedFacebookPage:
    return ValidatedFacebookPage(
        page_id=page_id,
        page_name="Clinic Page",
        instagram_id="",
        instagram_username="",
        channels=("facebook",),
        credential=_credential(page_id),
    )


@pytest.mark.asyncio
async def test_cleanup_waiter_reports_child_failure_after_caller_cancellation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def failing_cleanup() -> None:
        started.set()
        await release.wait()
        raise RuntimeError("simulated cleanup failure")

    cleanup = asyncio.create_task(failing_cleanup())
    waiter = asyncio.create_task(meta_oauth_activation._await_cleanup_shielded(cleanup))
    await asyncio.wait_for(started.wait(), timeout=1.0)
    waiter.cancel()
    await asyncio.sleep(0)
    assert not waiter.done()
    release.set()

    result, caller_cancelled, cleanup_error = await asyncio.wait_for(waiter, timeout=1.0)
    assert result is None
    assert caller_cancelled is True
    assert isinstance(cleanup_error, RuntimeError)


@pytest.mark.asyncio
async def test_caller_cancellation_wins_after_cleanup_child_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry(tmp_path, monkeypatch)
    write_started = asyncio.Event()

    async def inspect(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def subscribe(*_args: Any, **_kwargs: Any) -> None:
        write_started.set()
        await asyncio.Future()

    async def failing_cleanup(**_kwargs: Any) -> None:
        raise RuntimeError("simulated cleanup task failure")

    monkeypatch.setattr(meta_oauth_activation, "inspect_binding_webhook_subscription", inspect)
    monkeypatch.setattr(meta_oauth_activation, "subscribe_binding_webhook", subscribe)
    monkeypatch.setattr(meta_oauth_activation, "_compensate_and_discard_staged_bindings", failing_cleanup)

    task = asyncio.create_task(
        activate_validated_facebook_pages(
            [_validated_page("333444555")],
            tenant_id="linas",
            app_key=APP_A_KEY,
            actor_id="owner",
            registry=registry,
            client=SimpleNamespace(),
        )
    )
    await asyncio.wait_for(write_started.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)


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
