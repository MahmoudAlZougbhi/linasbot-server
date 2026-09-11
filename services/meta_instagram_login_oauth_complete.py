"""Complete Instagram Login OAuth and activate the staged Instagram credential."""

from __future__ import annotations

import asyncio
import hashlib
import time
from typing import cast

import httpx

from services.async_safety_cleanup import await_safety_task as _await_safety_task
from services.meta_app_registry import (
    APP_A_KEY,
    META_FORBIDDEN_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    MetaOAuthStateError,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_GRAPH_BASE_URL,
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
    META_INSTAGRAM_LOGIN_REQUIRED_SCOPES,
    instagram_login_app_id,
    instagram_login_app_secret,
    instagram_login_config_status,
    instagram_login_redirect_uri,
)
from services.meta_instagram_login_oauth_staging import (
    _authorize_staged_instagram_binding_reconciled,
    _compensate_failed_instagram_activation,
    _instagram_activation_commit_matches,
    _InstagramProviderVerificationDeferred,
    _mark_instagram_cleanup_pending,
)
from services.meta_instagram_login_oauth_tokens import (
    INSTAGRAM_LOGIN_OAUTH_FLOW,
    InstagramLoginOAuthResult,
    _tenant_has_recent_instagram_cleanup,
    exchange_instagram_long_lived_token,
    exchange_instagram_short_lived_token,
    fetch_instagram_login_profile,
    resolve_instagram_login_scopes,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR,
    INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR,
    INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR,
    ensure_instagram_login_webhook_subscription,
    inspect_instagram_login_webhook_subscription,
    instagram_channel_subscription_lock_asset,
    instagram_login_subscription_lock_asset,
)
from services.meta_instagram_login_subscription_recovery import retry_instagram_login_cleanup
from services.meta_oauth import MetaOAuthError
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionBlockedError,
    MetaSubjectDeletionGuardError,
    MetaSubjectDeletionLeaseBusyError,
    MetaSubjectDeletionStoreUnavailableError,
    acquire_meta_oauth_subject_guard,
    meta_deletion_subject_hmac,
)


async def complete_instagram_login(
    *,
    code: str,
    state: str,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginOAuthResult:
    status = instagram_login_config_status()
    if not status.configured:
        missing = ", ".join(status.missing)
        raise MetaOAuthError(f"Instagram Login is not configured. Missing: {missing}")
    if not code or not state:
        raise MetaOAuthStateError("OAuth code and state are required")
    current_registry = registry or get_meta_app_registry()
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    state_data = current_registry.consume_oauth_state(state_hash)
    if str(state_data.get("oauth_flow") or "") != INSTAGRAM_LOGIN_OAUTH_FLOW:
        raise MetaOAuthStateError("OAuth state flow does not match Instagram Login")
    if state_data.get("app_key") != APP_A_KEY:
        raise MetaOAuthStateError("OAuth state app does not match")
    redirect_uri = str(state_data.get("redirect_uri") or "")
    if redirect_uri != instagram_login_redirect_uri():
        raise MetaOAuthStateError("OAuth redirect does not match")
    tenant_id = str(state_data.get("tenant_id") or "").strip()
    actor_id = str(state_data.get("actor_id") or "oauth")
    oauth_started_at = float(state_data.get("created_at") or 0.0)
    if oauth_started_at <= 0.0 or oauth_started_at > time.time():
        raise MetaOAuthStateError("OAuth state creation time is invalid")
    from services.meta_oauth_return import normalize_return_surface

    return_surface = normalize_return_surface(state_data.get("return_surface"))
    requested = frozenset(
        str(scope) for scope in state_data.get("requested_scopes") or META_INSTAGRAM_LOGIN_REQUEST_SCOPES
    )
    if not tenant_id:
        raise MetaOAuthStateError("OAuth state binding is invalid")

    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=META_INSTAGRAM_GRAPH_BASE_URL, timeout=20.0)
    try:
        short_lived_token, authorized_user_id, short_payload = await exchange_instagram_short_lived_token(
            code=code,
            client=http_client,
        )
        long_lived_token, expires_at, long_payload = await exchange_instagram_long_lived_token(
            short_lived_token=short_lived_token,
            client=http_client,
        )
        profile = await fetch_instagram_login_profile(long_lived_token, client=http_client)
        instagram_id = profile["user_id"]
        instagram_username = profile["username"]
        scopes, declined = resolve_instagram_login_scopes(
            requested_scopes=requested,
            token_payloads=[short_payload, long_payload],
        )
        if not META_INSTAGRAM_LOGIN_REQUIRED_SCOPES.issubset(scopes):
            raise MetaOAuthError("Instagram Login did not grant required messaging permissions")
        if set(scopes) & META_FORBIDDEN_SCOPES:
            raise MetaOAuthError("Instagram token includes a prohibited permission")

        credential = MetaBindingCredential(
            access_token=long_lived_token,
            token_app_id=instagram_login_app_id(),
            token_profile_id=instagram_id,
            scopes=scopes,
            expires_at=expires_at,
            authorized_meta_user_id=authorized_user_id,
            auth_flow="instagram_login",
            declined_scopes=declined,
            authorization_started_at=oauth_started_at,
        )
        subject_key = meta_deletion_subject_hmac(
            app_key=APP_A_KEY,
            app_id=instagram_login_app_id(),
            auth_flow="instagram_login",
            meta_user_id=authorized_user_id,
            app_secret=instagram_login_app_secret(),
        )
        try:
            subject_guard = acquire_meta_oauth_subject_guard(
                subject_key,
                oauth_started_at=oauth_started_at,
            )
        except MetaSubjectDeletionBlockedError as exc:
            if exc.state == "failed":
                raise MetaOAuthError("Instagram authorization is blocked by a failed data deletion request") from exc
            if exc.state == "pending":
                raise MetaOAuthError("Instagram authorization is blocked by a pending data deletion request") from exc
            raise MetaOAuthError("Instagram authorization safety guard changed during authorization") from exc
        except MetaSubjectDeletionLeaseBusyError as exc:
            raise MetaOAuthError("Instagram authorization is already in progress. Try again shortly.") from exc
        except MetaSubjectDeletionStoreUnavailableError as exc:
            raise MetaOAuthError("Instagram authorization safety guard is temporarily unavailable") from exc
        except MetaSubjectDeletionGuardError as exc:
            raise MetaOAuthError("Instagram authorization safety guard failed") from exc

        with subject_guard:
            async with lock_facebook_page_oauth_operation(
                current_registry,
                app_key=APP_A_KEY,
                page_ids=(
                    instagram_channel_subscription_lock_asset(tenant_id),
                    instagram_login_subscription_lock_asset(instagram_id),
                ),
            ):
                previous_active = next(
                    (
                        item
                        for item in current_registry.list_bindings(include_inactive=False, include_superseded=True)
                        if item.tenant_id == tenant_id
                        and item.channel == "instagram"
                        and item.asset_id == instagram_id
                        and item.app_key == APP_A_KEY
                    ),
                    None,
                )
                if _tenant_has_recent_instagram_cleanup(
                    current_registry,
                    tenant_id=tenant_id,
                    now=time.time(),
                ):
                    raise MetaOAuthError("Instagram webhook subscription cleanup is in progress. Try again shortly.")
                binding = _authorize_staged_instagram_binding_reconciled(
                    registry=current_registry,
                    tenant_id=tenant_id,
                    instagram_id=instagram_id,
                    instagram_username=instagram_username,
                    credential=credential,
                    actor_id=actor_id,
                )
                app = get_meta_app_configs()[APP_A_KEY]
                provider_write_started = False
                provider_preimage: tuple[str, ...] | None = None
                try:
                    current_registry.assert_binding_can_activate(
                        binding.binding_id,
                        expected_generation=binding.generation,
                        replacing_binding_id=previous_active.binding_id if previous_active is not None else "",
                    )
                    provider_preimage = await inspect_instagram_login_webhook_subscription(
                        binding,
                        registry=current_registry,
                        client=http_client,
                    )
                    provider_write_started = True
                    subscription = await ensure_instagram_login_webhook_subscription(
                        binding,
                        credential,
                        registry=current_registry,
                        graph_api_version=app.graph_api_version,
                        client=http_client,
                    )
                    if subscription.error == INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR:
                        provider_write_started = False
                    staged = next(
                        item
                        for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                        if item.binding_id == binding.binding_id
                    )
                    if subscription.error in {
                        INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR,
                        INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR,
                    }:
                        detail = (
                            "Instagram rate-limited webhook setup (Graph error 613). "
                            if subscription.error == INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR
                            else "Instagram did not confirm webhook fields after two checks. "
                        )
                        raise _InstagramProviderVerificationDeferred(f"{detail}Do not tap Connect again.")
                    if not subscription.ready_for_dm or not subscription.ready_for_comments:
                        raise MetaOAuthError(
                            "Instagram webhook subscription could not be confirmed. Reconnect Instagram and try again."
                        )
                    try:
                        subject_guard.assert_oauth_snapshot_unchanged()
                    except MetaSubjectDeletionStoreUnavailableError as exc:
                        raise MetaOAuthError("Instagram authorization safety guard is temporarily unavailable") from exc
                    except MetaSubjectDeletionGuardError as exc:
                        raise MetaOAuthError(
                            "Instagram authorization safety guard changed because deletion state changed during authorization"
                        ) from exc
                    binding = current_registry.activate_staged_binding(
                        staged.binding_id,
                        actor_id=actor_id,
                        expected_generation=staged.generation,
                        replace_existing=previous_active is not None,
                    )
                except BaseException as operation_error:  # noqa: BLE001 - cancellation must compensate too
                    latest = next(
                        (
                            item
                            for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                            if item.binding_id == binding.binding_id
                        ),
                        None,
                    )
                    if _instagram_activation_commit_matches(
                        latest,
                        staged=binding,
                        registry=current_registry,
                    ):
                        binding = cast(MetaAssetBinding, latest)
                        if isinstance(operation_error, asyncio.CancelledError):
                            raise
                    else:
                        if isinstance(operation_error, _InstagramProviderVerificationDeferred):
                            restore_target = (
                                provider_preimage
                                if previous_active is not None and previous_active.auth_flow == "instagram_login"
                                else None
                            )
                            try:
                                _mark_instagram_cleanup_pending(
                                    binding,
                                    restore_target=restore_target,
                                    registry=current_registry,
                                )
                            except Exception as marker_error:
                                raise MetaOAuthError(
                                    "Instagram cleanup state could not be persisted; operator recovery required"
                                ) from marker_error
                            raise
                        cleanup_task = asyncio.create_task(
                            _compensate_failed_instagram_activation(
                                binding,
                                previous_active=previous_active,
                                provider_preimage=provider_preimage,
                                provider_write_started=provider_write_started,
                                actor_id=actor_id,
                                registry=current_registry,
                                client=http_client,
                            )
                        )
                        _unused, cleanup_cancelled, cleanup_error = await _await_safety_task(cleanup_task)
                        if cleanup_error is not None:
                            restore_target = (
                                provider_preimage
                                if previous_active is not None and previous_active.auth_flow == "instagram_login"
                                else None
                            )
                            try:
                                _mark_instagram_cleanup_pending(
                                    binding,
                                    restore_target=restore_target,
                                    registry=current_registry,
                                )
                            except Exception as marker_error:
                                raise MetaOAuthError(
                                    "Instagram cleanup state could not be persisted; operator recovery required"
                                ) from marker_error
                            raise MetaOAuthError(
                                "Instagram provider subscription cleanup failed; retry before reconnecting"
                            ) from cleanup_error
                        if isinstance(operation_error, asyncio.CancelledError) or cleanup_cancelled:
                            raise asyncio.CancelledError from operation_error
                        raise operation_error
                pending_cleanup_ids = [
                    item.binding_id
                    for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                    if item.binding_id != binding.binding_id
                    and item.tenant_id == tenant_id
                    and item.channel == "instagram"
                    and item.asset_id == instagram_id
                    and item.app_key == APP_A_KEY
                    and item.auth_flow == "instagram_login"
                    and item.webhook_subscription_status == INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
                    and current_registry.binding_credential_is_available(item.binding_id)
                ]
                for pending_binding_id in pending_cleanup_ids:
                    try:
                        await retry_instagram_login_cleanup(
                            pending_binding_id,
                            registry=current_registry,
                            actor_id=actor_id,
                            client=http_client,
                        )
                    except Exception:
                        # The fresh owner is already committed and routable.
                        # Durable recovery will retry stale marker cleanup.
                        continue
        current_registry.archive_superseded_duplicate_bindings(actor_id=actor_id)
        from services.channel_capability_toggles import enable_channel_defaults_after_connect

        try:
            await enable_channel_defaults_after_connect(
                tenant_id=tenant_id,
                platform="instagram",
                actor=actor_id,
            )
        except Exception:
            pass
        return InstagramLoginOAuthResult(
            binding=binding,
            instagram_username=instagram_username,
            granted_scopes=scopes,
            declined_scopes=declined,
            return_surface=return_surface,
        )
    finally:
        if owns_client:
            await http_client.aclose()
