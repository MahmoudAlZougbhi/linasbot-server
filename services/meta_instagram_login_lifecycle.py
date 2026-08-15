"""Startup/shutdown lifecycle for Instagram Login subscription recovery and token refresh."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.meta_app_registry import MetaRegistryError, get_meta_app_registry
from services.meta_instagram_login_capabilities import instagram_login_subscription_retry_eligible
from services.meta_instagram_login_config import instagram_login_config_status
from services.meta_instagram_login_oauth import credential_needs_refresh
from services.meta_instagram_login_subscription import INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
from services.meta_instagram_login_subscription_recovery import (
    instagram_login_orphan_cleanup_eligible,
    retry_instagram_login_cleanup,
    retry_instagram_login_orphan_cleanup,
    retry_instagram_login_webhook_subscription,
)
from services.meta_instagram_login_tokens import refresh_binding_instagram_login_token
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_graph import disconnect_binding_webhook

_runtime_logger = logging.getLogger("uvicorn.error")

_TICK_LOCK_ID = "instagram-login-lifecycle-tick"
_TICK_INTERVAL_SECONDS = 300.0
_MAX_BINDINGS_PER_TICK = 20

_lifecycle: InstagramLoginLifecycle | None = None


class InstagramLoginLifecycle:
    def __init__(self) -> None:
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop(), name="instagram-login-lifecycle")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def run_once(self, *, actor_id: str = "instagram-login-lifecycle") -> dict[str, int]:
        instagram_configured = instagram_login_config_status().configured
        if not try_acquire_job_lock(_TICK_LOCK_ID, ttl_seconds=_TICK_INTERVAL_SECONDS + 60.0):
            return {
                "disconnects_recovered": 0,
                "cleanups_recovered": 0,
                "orphans_recovered": 0,
                "subscriptions_recovered": 0,
                "tokens_refreshed": 0,
                "skipped": 1,
            }
        try:
            return await self._run_cycle(
                actor_id=actor_id,
                instagram_configured=instagram_configured,
            )
        finally:
            release_job_lock(_TICK_LOCK_ID)

    async def _run_cycle(self, *, actor_id: str, instagram_configured: bool = True) -> dict[str, int]:
        registry = get_meta_app_registry()
        disconnects_recovered = 0
        cleanups_recovered = 0
        orphans_recovered = 0
        subscriptions_recovered = 0
        tokens_refreshed = 0
        cleanup_checked = 0
        orphan_checked = 0
        active_checked = 0
        disconnect_checked = 0
        pending_disconnects = sorted(
            (
                binding
                for binding in registry.list_bindings(include_inactive=True, include_superseded=True)
                if binding.status == "disconnected" and registry.binding_credential_is_available(binding.binding_id)
            ),
            key=lambda binding: (
                binding.webhook_subscription_checked_at,
                binding.updated_at,
                binding.binding_id,
            ),
        )
        for binding in pending_disconnects:
            if disconnect_checked >= _MAX_BINDINGS_PER_TICK:
                break
            disconnect_checked += 1
            try:
                await disconnect_binding_webhook(
                    binding,
                    actor_id=actor_id,
                    registry=registry,
                )
                disconnects_recovered += 1
            except (MetaOAuthError, MetaRegistryError) as exc:
                try:
                    registry.record_binding_recovery_attempt(
                        binding.binding_id,
                        actor_id=actor_id,
                        expected_generation=binding.generation,
                    )
                except MetaRegistryError:
                    pass
                _runtime_logger.warning(
                    "[instagram-login] lifecycle_disconnect_failed binding=%s reason=%s",
                    binding.binding_id[-8:],
                    type(exc).__name__,
                )
        pending_cleanups = sorted(
            (
                binding
                for binding in registry.list_bindings(include_inactive=True, include_superseded=True)
                if binding.auth_flow == "instagram_login"
                and binding.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
                and registry.binding_credential_is_available(binding.binding_id)
            ),
            key=lambda binding: (
                binding.webhook_subscription_checked_at,
                binding.updated_at,
                binding.binding_id,
            ),
        )
        for binding in pending_cleanups:
            if cleanup_checked >= _MAX_BINDINGS_PER_TICK:
                break
            cleanup_checked += 1
            try:
                await retry_instagram_login_cleanup(
                    binding.binding_id,
                    registry=registry,
                    actor_id=actor_id,
                )
                cleanups_recovered += 1
            except (MetaOAuthError, MetaRegistryError) as exc:
                try:
                    registry.record_binding_recovery_attempt(
                        binding.binding_id,
                        actor_id=actor_id,
                        expected_generation=binding.generation,
                    )
                except MetaRegistryError:
                    pass
                _runtime_logger.warning(
                    "[instagram-login] lifecycle_cleanup_failed binding=%s reason=%s",
                    binding.binding_id[-8:],
                    type(exc).__name__,
                )
        pending_orphans = sorted(
            (
                binding
                for binding in registry.list_bindings(include_inactive=True, include_superseded=True)
                if instagram_login_orphan_cleanup_eligible(binding)
                and registry.binding_credential_is_available(binding.binding_id)
            ),
            key=lambda binding: (
                binding.webhook_subscription_checked_at,
                binding.updated_at,
                binding.binding_id,
            ),
        )
        for binding in pending_orphans:
            if orphan_checked >= _MAX_BINDINGS_PER_TICK:
                break
            orphan_checked += 1
            try:
                await retry_instagram_login_orphan_cleanup(
                    binding.binding_id,
                    registry=registry,
                    actor_id=actor_id,
                )
                orphans_recovered += 1
            except (MetaOAuthError, MetaRegistryError) as exc:
                try:
                    registry.record_binding_recovery_attempt(
                        binding.binding_id,
                        actor_id=actor_id,
                        expected_generation=binding.generation,
                    )
                except MetaRegistryError:
                    pass
                _runtime_logger.warning(
                    "[instagram-login] lifecycle_orphan_cleanup_failed binding=%s reason=%s",
                    binding.binding_id[-8:],
                    type(exc).__name__,
                )
        if not instagram_configured:
            checked = disconnect_checked + cleanup_checked + orphan_checked
            return {
                "disconnects_recovered": disconnects_recovered,
                "cleanups_recovered": cleanups_recovered,
                "orphans_recovered": orphans_recovered,
                "subscriptions_recovered": subscriptions_recovered,
                "tokens_refreshed": tokens_refreshed,
                "checked": checked,
                "disconnect_checked": disconnect_checked,
                "cleanup_checked": cleanup_checked,
                "orphan_checked": orphan_checked,
                "active_checked": active_checked,
            }
        for binding in registry.list_bindings(include_inactive=False):
            if active_checked >= _MAX_BINDINGS_PER_TICK:
                break
            if binding.auth_flow != "instagram_login" or binding.status != "active":
                continue
            try:
                credential = registry.get_credential(binding)
            except Exception:
                continue
            if credential.expires_at is not None and credential.expires_at <= int(time.time()):
                active_checked += 1
                try:
                    registry.set_binding_status(
                        binding.binding_id,
                        status="disconnected",
                        actor_id=actor_id,
                        expected_generation=binding.generation,
                    )
                except MetaRegistryError as exc:
                    _runtime_logger.warning(
                        "[instagram-login] lifecycle_expired_disconnect_failed binding=%s reason=%s",
                        binding.binding_id[-8:],
                        type(exc).__name__,
                    )
                continue
            if instagram_login_subscription_retry_eligible(binding, credential):
                active_checked += 1
                try:
                    state = await retry_instagram_login_webhook_subscription(
                        binding.binding_id,
                        registry=registry,
                        actor_id=actor_id,
                    )
                    if state.ready_for_dm:
                        subscriptions_recovered += 1
                except (MetaOAuthError, MetaRegistryError) as exc:
                    _runtime_logger.warning(
                        "[instagram-login] lifecycle_subscribe_failed binding=%s reason=%s",
                        binding.binding_id[-8:],
                        type(exc).__name__,
                    )
                continue
            if credential_needs_refresh(credential):
                active_checked += 1
                try:
                    await refresh_binding_instagram_login_token(binding, registry=registry)
                    tokens_refreshed += 1
                except (MetaOAuthError, MetaRegistryError) as exc:
                    _runtime_logger.warning(
                        "[instagram-login] lifecycle_refresh_failed binding=%s reason=%s",
                        binding.binding_id[-8:],
                        type(exc).__name__,
                    )
        checked = disconnect_checked + cleanup_checked + orphan_checked + active_checked
        if checked:
            _runtime_logger.info(
                "[instagram-login] lifecycle_cycle disconnects_recovered=%d cleanups_recovered=%d "
                "orphans_recovered=%d subscriptions_recovered=%d tokens_refreshed=%d "
                "disconnect_checked=%d cleanup_checked=%d orphan_checked=%d active_checked=%d",
                disconnects_recovered,
                cleanups_recovered,
                orphans_recovered,
                subscriptions_recovered,
                tokens_refreshed,
                disconnect_checked,
                cleanup_checked,
                orphan_checked,
                active_checked,
            )
        return {
            "disconnects_recovered": disconnects_recovered,
            "cleanups_recovered": cleanups_recovered,
            "orphans_recovered": orphans_recovered,
            "subscriptions_recovered": subscriptions_recovered,
            "tokens_refreshed": tokens_refreshed,
            "checked": checked,
            "disconnect_checked": disconnect_checked,
            "cleanup_checked": cleanup_checked,
            "orphan_checked": orphan_checked,
            "active_checked": active_checked,
        }

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.run_once(actor_id="instagram-login-scheduler")
            except Exception as exc:
                _runtime_logger.error("[instagram-login] lifecycle_loop_error type=%s", type(exc).__name__)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=_TICK_INTERVAL_SECONDS)
            except TimeoutError:
                continue


def get_instagram_login_lifecycle() -> InstagramLoginLifecycle:
    global _lifecycle
    if _lifecycle is None:
        _lifecycle = InstagramLoginLifecycle()
    return _lifecycle


def schedule_instagram_login_lifecycle(app_state: Any) -> None:
    lifecycle = get_instagram_login_lifecycle()
    app_state.instagram_login_lifecycle = lifecycle


async def start_instagram_login_lifecycle(app_state: Any) -> None:
    schedule_instagram_login_lifecycle(app_state)
    await app_state.instagram_login_lifecycle.start()


async def stop_instagram_login_lifecycle(app_state: Any) -> None:
    lifecycle = getattr(app_state, "instagram_login_lifecycle", None)
    if lifecycle is not None:
        await lifecycle.stop()
