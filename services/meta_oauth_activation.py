"""Atomic local activation and compensating Page webhook mutation for Meta OAuth."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace

import httpx

from services.async_safety_cleanup import await_safety_task as _await_cleanup_shielded
from services.meta_app_registry import (
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    MetaChannel,
    get_meta_app_configs,
)
from services.meta_oauth_graph import (
    MetaOAuthError,
    PageWebhookSubscriptionSnapshot,
    _restore_binding_webhook_subscription_locked,
    desired_binding_webhook_subscription,
    inspect_binding_webhook_subscription,
    subscribe_binding_webhook,
)
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation
from services.meta_page_subscription_transaction import reconcile_page_activation_after_exception
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionBlockedError,
    MetaSubjectDeletionGuardError,
    MetaSubjectDeletionLeaseBusyError,
    MetaSubjectDeletionStoreUnavailableError,
    acquire_meta_oauth_subject_guard,
    meta_deletion_subject_hmac,
)


@dataclass(frozen=True)
class ValidatedFacebookPage:
    page_id: str
    page_name: str
    instagram_id: str
    instagram_username: str
    channels: tuple[MetaChannel, ...]
    credential: MetaBindingCredential


def _discard_staged_bindings(
    registry: MetaAppRegistry,
    staged: list[MetaAssetBinding],
    *,
    actor_id: str,
) -> None:
    latest_by_id = {
        binding.binding_id: binding
        for binding in registry.list_bindings(include_inactive=True, include_superseded=True)
    }
    for original in staged:
        latest = latest_by_id.get(original.binding_id)
        if latest is not None and not latest.active:
            registry.discard_staged_binding(
                latest.binding_id,
                actor_id=actor_id,
                expected_generation=latest.generation,
            )


async def _compensate_and_discard_staged_bindings(
    *,
    attempted: list[MetaAssetBinding],
    staged: list[MetaAssetBinding],
    snapshots: dict[str, PageWebhookSubscriptionSnapshot],
    expected_after_write: dict[str, tuple[str, ...]],
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
) -> bool:
    """Restore provider state, then discard local staging when restoration is safe."""

    compensation_failed = False
    for binding in reversed(attempted):
        try:
            # Cleanup runs in its own shielded Task while the parent still owns
            # the outer Page lock. Call the locked primitive directly rather than
            # falsely treating the child Task as a re-entrant lock owner.
            await _restore_binding_webhook_subscription_locked(
                binding,
                snapshots[binding.binding_id],
                expected_current=expected_after_write[binding.binding_id],
                registry=registry,
                client=client,
            )
        except Exception:
            compensation_failed = True
    if not compensation_failed:
        _discard_staged_bindings(registry, staged, actor_id=actor_id)
    return compensation_failed


async def activate_validated_facebook_pages(
    pages: list[ValidatedFacebookPage],
    *,
    tenant_id: str,
    app_key: str,
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
    oauth_started_at: float = 0.0,
) -> tuple[MetaAssetBinding, ...]:
    """Preflight all Pages, mutate all subscriptions, then cut over atomically."""

    async with lock_facebook_page_oauth_operation(
        registry,
        app_key=app_key,
        page_ids=tuple(page.page_id for page in pages),
    ):
        return await _activate_validated_facebook_pages_locked(
            pages,
            tenant_id=tenant_id,
            app_key=app_key,
            actor_id=actor_id,
            registry=registry,
            client=client,
            oauth_started_at=oauth_started_at,
        )


async def _activate_validated_facebook_pages_locked(
    pages: list[ValidatedFacebookPage],
    *,
    tenant_id: str,
    app_key: str,
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
    oauth_started_at: float = 0.0,
) -> tuple[MetaAssetBinding, ...]:
    """Run one Page-set OAuth transaction while its durable locks are held."""

    authorized_subjects = {
        str(page.credential.authorized_meta_user_id or "").strip()
        for page in pages
        if str(page.credential.authorized_meta_user_id or "").strip()
    }
    if len(authorized_subjects) != 1 or any(page.credential.auth_flow != "facebook_login" for page in pages):
        raise MetaOAuthError("Meta Page authorization subject is inconsistent")
    app = get_meta_app_configs().get(app_key)
    if app is None or not app.enabled:
        raise MetaOAuthError("Meta Page authorization app is unavailable")
    subject_key = meta_deletion_subject_hmac(
        app_key=app_key,
        app_id=app.app_id,
        auth_flow="facebook_login",
        meta_user_id=next(iter(authorized_subjects)),
        app_secret=app.app_secret,
    )
    try:
        subject_guard = acquire_meta_oauth_subject_guard(
            subject_key,
            oauth_started_at=oauth_started_at,
        )
    except MetaSubjectDeletionBlockedError as exc:
        if exc.state == "failed":
            raise MetaOAuthError("Meta authorization is blocked by a failed data deletion request") from exc
        if exc.state == "pending":
            raise MetaOAuthError("Meta authorization is blocked by a pending data deletion request") from exc
        raise MetaOAuthError("Meta authorization safety guard changed during authorization") from exc
    except MetaSubjectDeletionLeaseBusyError as exc:
        raise MetaOAuthError("Meta authorization is already in progress. Try again shortly.") from exc
    except MetaSubjectDeletionStoreUnavailableError as exc:
        raise MetaOAuthError("Meta authorization safety guard is temporarily unavailable") from exc
    except MetaSubjectDeletionGuardError as exc:
        raise MetaOAuthError("Meta authorization safety guard failed") from exc

    staged: list[MetaAssetBinding] = []
    attempted: list[MetaAssetBinding] = []
    snapshots: dict[str, PageWebhookSubscriptionSnapshot] = {}
    expected_after_write: dict[str, tuple[str, ...]] = {}
    with subject_guard:
        try:
            for page in pages:
                for channel in page.channels:
                    asset_id = page.page_id if channel == "facebook" else page.instagram_id
                    staged.append(
                        registry.authorize_oauth_asset(
                            tenant_id=tenant_id,
                            channel=channel,
                            asset_id=asset_id,
                            page_id=page.page_id,
                            instagram_account_id=page.instagram_id,
                            app_key=app_key,
                            credential=page.credential,
                            actor_id=actor_id,
                            page_name=page.page_name,
                            instagram_username=page.instagram_username,
                            status="testing",
                            webhook_subscription_status="unknown",
                            webhook_subscribed_fields=(),
                            webhook_subscription_error="",
                            webhook_subscription_checked_at=0.0,
                            create_new_binding=True,
                        )
                    )
            for binding in staged:
                snapshots[binding.binding_id] = await inspect_binding_webhook_subscription(
                    binding,
                    registry=registry,
                    client=client,
                )
            from services.channel_capability_toggles import (
                ChannelToggleError,
                enable_channel_defaults_after_connect,
            )

            for channel in sorted({binding.channel for binding in staged}):
                try:
                    await enable_channel_defaults_after_connect(
                        tenant_id=tenant_id,
                        platform=channel,
                        actor=actor_id,
                        include_comments=False,
                    )
                except ChannelToggleError as exc:
                    raise MetaOAuthError("Facebook Messages could not be enabled after Connect") from exc
            for binding in staged:
                active_binding = replace(binding, status="active")
                expected_after_write[binding.binding_id] = desired_binding_webhook_subscription(
                    active_binding,
                    registry=registry,
                )
                attempted.append(binding)
                await subscribe_binding_webhook(
                    active_binding,
                    registry=registry,
                    client=client,
                )
            try:
                subject_guard.assert_oauth_snapshot_unchanged()
            except MetaSubjectDeletionStoreUnavailableError as exc:
                raise MetaOAuthError("Meta authorization safety guard is temporarily unavailable") from exc
            except MetaSubjectDeletionGuardError as exc:
                raise MetaOAuthError(
                    "Meta authorization safety guard changed because deletion state changed during authorization"
                ) from exc
            return registry.activate_staged_bindings(
                tuple(binding.binding_id for binding in staged),
                actor_id=actor_id,
                expected_generations={binding.binding_id: binding.generation for binding in staged},
                replace_existing=True,
            )
        except BaseException as exc:
            try:
                committed = reconcile_page_activation_after_exception(
                    tuple(staged),
                    expected_fields=expected_after_write,
                    registry=registry,
                )
            except MetaOAuthError as reconciliation_error:
                if isinstance(exc, asyncio.CancelledError):
                    raise exc from reconciliation_error
                raise reconciliation_error from exc
            if committed is not None:
                # The database commit won but its acknowledgement was lost.
                # Restoring provider preimages would sever the now-active rows.
                if isinstance(exc, asyncio.CancelledError):
                    raise
                return committed
            cleanup_task = asyncio.create_task(
                _compensate_and_discard_staged_bindings(
                    attempted=attempted,
                    staged=staged,
                    snapshots=snapshots,
                    expected_after_write=expected_after_write,
                    actor_id=actor_id,
                    registry=registry,
                    client=client,
                )
            )
            cleanup_result, cancelled_during_cleanup, cleanup_error = await _await_cleanup_shielded(cleanup_task)
            if isinstance(exc, asyncio.CancelledError):
                # The caller still receives cancellation, but only after provider
                # compensation and safe staged-record disposal have finished.
                raise
            if cancelled_during_cleanup:
                raise asyncio.CancelledError from exc
            if cleanup_error is not None:
                raise MetaOAuthError("Meta staged authorization cleanup could not complete") from cleanup_error
            compensation_failed = bool(cleanup_result)
            if compensation_failed:
                raise MetaOAuthError(
                    "Meta Page webhook compensation could not be verified; staged bindings were retained"
                ) from exc
            raise
