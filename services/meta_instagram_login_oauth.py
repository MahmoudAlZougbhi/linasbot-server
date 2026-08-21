"""Instagram API with Instagram Login OAuth for Meta App A."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlencode

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
    normalize_meta_tenant_id,
)
from services.meta_instagram_login_config import (
    META_INSTAGRAM_GRAPH_BASE_URL,
    META_INSTAGRAM_LOGIN_REQUEST_SCOPES,
    META_INSTAGRAM_LOGIN_REQUIRED_SCOPES,
    META_INSTAGRAM_OAUTH_AUTHORIZE_URL,
    META_INSTAGRAM_OAUTH_TOKEN_URL,
    instagram_login_app_id,
    instagram_login_app_secret,
    instagram_login_config_status,
    instagram_login_redirect_uri,
    instagram_login_refresh_lead_seconds,
)
from services.meta_instagram_login_subscription import (
    INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR,
    INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
    INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR,
    InstagramLoginSubscriptionState,
    ensure_instagram_login_webhook_subscription,
    inspect_instagram_login_webhook_subscription,
    instagram_channel_subscription_lock_asset,
    instagram_login_subscription_lock_asset,
    restore_instagram_login_webhook_subscription,
)
from services.meta_instagram_login_subscription_recovery import retry_instagram_login_cleanup
from services.meta_oauth import META_OAUTH_STATE_TTL_SECONDS, MetaOAuthError, _safe_json
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation
from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionBlockedError,
    MetaSubjectDeletionGuardError,
    MetaSubjectDeletionLeaseBusyError,
    MetaSubjectDeletionStoreUnavailableError,
    acquire_meta_oauth_subject_guard,
    meta_deletion_subject_hmac,
)

INSTAGRAM_LOGIN_OAUTH_FLOW = "instagram_login"


@dataclass(frozen=True)
class InstagramLoginOAuthResult:
    binding: MetaAssetBinding
    instagram_username: str
    granted_scopes: tuple[str, ...]
    declined_scopes: tuple[str, ...]
    return_surface: str = "web"


def begin_instagram_login(
    *,
    tenant_id: str,
    actor_id: str,
    return_surface: str = "web",
    registry: MetaAppRegistry | None = None,
) -> str:
    from services.meta_oauth_return import normalize_return_surface

    status = instagram_login_config_status()
    if not status.configured:
        missing = ", ".join(status.missing)
        raise MetaOAuthError(f"Instagram Login is not configured. Missing: {missing}")
    try:
        tenant = normalize_meta_tenant_id(tenant_id)
    except Exception as exc:
        raise MetaOAuthError("Tenant is unavailable for this session") from exc

    nonce = secrets.token_urlsafe(32)
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    actor_reference = hashlib.sha256(str(actor_id or "oauth").encode("utf-8")).hexdigest()[:16]
    surface = normalize_return_surface(return_surface)
    current_registry = registry or get_meta_app_registry()
    oauth_started_at = time.time()
    current_registry.store_oauth_state(
        nonce_hash,
        {
            "tenant_id": tenant,
            "oauth_flow": INSTAGRAM_LOGIN_OAUTH_FLOW,
            "actor_id": f"oauth:{actor_reference}",
            "app_key": APP_A_KEY,
            "redirect_uri": instagram_login_redirect_uri(),
            "requested_scopes": sorted(META_INSTAGRAM_LOGIN_REQUEST_SCOPES),
            "return_surface": surface,
            "created_at": oauth_started_at,
            "expires_at": oauth_started_at + META_OAUTH_STATE_TTL_SECONDS,
        },
    )
    query = urlencode(
        {
            "client_id": instagram_login_app_id(),
            "redirect_uri": instagram_login_redirect_uri(),
            "response_type": "code",
            "scope": ",".join(sorted(META_INSTAGRAM_LOGIN_REQUEST_SCOPES)),
            "state": nonce,
            # Meta: force_reauth fixes broken Instagram Login on mobile when the
            # user is already signed into Instagram (not a second OAuth path).
            "force_reauth": "true",
        }
    )
    return f"{META_INSTAGRAM_OAUTH_AUTHORIZE_URL}?{query}"


async def _graph_instagram_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    step: str,
    params: dict[str, str],
) -> dict[str, Any]:
    try:
        response = await client.get(path, params=params)
    except httpx.HTTPError as exc:
        raise MetaOAuthError(f"Instagram {step} request failed") from exc
    return _safe_json(response, step=step)


def _scopes_from_payload(payload: dict[str, Any]) -> tuple[str, ...]:
    raw = payload.get("granted_scopes") or payload.get("scope") or payload.get("permissions")
    if isinstance(raw, str):
        return tuple(sorted({item.strip() for item in raw.replace(",", " ").split() if item.strip()}))
    if isinstance(raw, list):
        return tuple(sorted({str(item).strip() for item in raw if str(item).strip()}))
    return ()


def resolve_instagram_login_scopes(
    *,
    requested_scopes: frozenset[str],
    token_payloads: list[dict[str, Any]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    granted: set[str] = set()
    for payload in token_payloads:
        granted.update(_scopes_from_payload(payload))
    if not granted:
        raise MetaOAuthError("Instagram Login did not return granted scopes in token exchange")
    declined = sorted(requested_scopes - granted)
    return tuple(sorted(granted)), tuple(declined)


async def exchange_instagram_short_lived_token(
    *,
    code: str,
    client: httpx.AsyncClient,
) -> tuple[str, str, dict[str, Any]]:
    try:
        response = await client.post(
            META_INSTAGRAM_OAUTH_TOKEN_URL,
            data={
                "client_id": instagram_login_app_id(),
                "client_secret": instagram_login_app_secret(),
                "grant_type": "authorization_code",
                "redirect_uri": instagram_login_redirect_uri(),
                "code": code,
            },
        )
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram authorization-code exchange failed") from exc
    payload = _safe_json(response, step="authorization-code exchange")
    access_token = str(payload.get("access_token") or "").strip()
    user_id = str(payload.get("user_id") or "").strip()
    if not access_token or not user_id.isdigit():
        error_type = str(payload.get("error_type") or payload.get("error") or "").strip()
        error_message = str(payload.get("error_message") or payload.get("error_description") or "").strip()
        detail = error_type or error_message or "missing access_token"
        raise MetaOAuthError(f"Instagram authorization-code exchange failed ({detail})")
    return access_token, user_id, payload


async def exchange_instagram_long_lived_token(
    *,
    short_lived_token: str,
    client: httpx.AsyncClient,
) -> tuple[str, int | None, dict[str, Any]]:
    payload = await _graph_instagram_get(
        client,
        "access_token",
        step="long-lived token exchange",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": instagram_login_app_secret(),
            "access_token": short_lived_token,
        },
    )
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise MetaOAuthError("Instagram long-lived token exchange failed")
    expires_in = payload.get("expires_in")
    expires_at = int(time.time()) + int(expires_in) if isinstance(expires_in, int) and expires_in > 0 else None
    return access_token, expires_at, payload


async def refresh_instagram_long_lived_token(access_token: str, *, client: httpx.AsyncClient) -> tuple[str, int | None]:
    payload = await _graph_instagram_get(
        client,
        "refresh_access_token",
        step="token refresh",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": access_token,
        },
    )
    refreshed = str(payload.get("access_token") or "").strip()
    if not refreshed:
        raise MetaOAuthError("Instagram token refresh failed")
    expires_in = payload.get("expires_in")
    expires_at = int(time.time()) + int(expires_in) if isinstance(expires_in, int) and expires_in > 0 else None
    return refreshed, expires_at


async def fetch_instagram_login_profile(access_token: str, *, client: httpx.AsyncClient) -> dict[str, str]:
    app = get_meta_app_configs()[APP_A_KEY]
    payload = await _graph_instagram_get(
        client,
        f"{app.graph_api_version}/me",
        step="profile discovery",
        params={
            "fields": "user_id,username,id",
            "access_token": access_token,
        },
    )
    user_id = str(payload.get("user_id") or payload.get("id") or "").strip()
    username = str(payload.get("username") or "").strip()
    if not user_id.isdigit():
        raise MetaOAuthError("Instagram profile discovery did not return a professional account id")
    return {"user_id": user_id, "username": username}


def credential_needs_refresh(
    credential: MetaBindingCredential,
    *,
    within_seconds: int | None = None,
) -> bool:
    lead = within_seconds if within_seconds is not None else instagram_login_refresh_lead_seconds()
    if credential.expires_at is None:
        return False
    now = int(time.time())
    if credential.expires_at <= now:
        return True
    return credential.expires_at <= now + lead


def _discard_staged_instagram_binding_reconciled(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry,
) -> MetaAssetBinding:
    """Discard one staged credential and accept only an exact lost acknowledgement."""

    try:
        return registry.discard_staged_binding(
            binding.binding_id,
            actor_id=actor_id,
            expected_generation=binding.generation,
        )
    except Exception:
        latest = next(
            (
                item
                for item in registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            None,
        )
        if (
            latest is None
            or latest.tenant_id != binding.tenant_id
            or latest.channel != binding.channel
            or latest.asset_id != binding.asset_id
            or latest.app_key != binding.app_key
            or latest.auth_flow != binding.auth_flow
            or latest.status != "disconnected"
            or registry.binding_credential_is_available(binding.binding_id)
        ):
            raise
        return latest


def _mark_instagram_cleanup_pending(
    binding: MetaAssetBinding,
    *,
    restore_target: tuple[str, ...] | None,
    registry: MetaAppRegistry,
) -> MetaAssetBinding:
    """Persist enough non-secret provider preimage for startup/periodic recovery."""

    error = (
        INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR if restore_target is not None else INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR
    )
    state = InstagramLoginSubscriptionState(
        status=INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS,
        subscribed_fields=tuple(restore_target or ()),
        verified_fields=tuple(restore_target or ()),
        error=error,
    )
    try:
        return cast(
            MetaAssetBinding,
            registry.update_instagram_login_webhook_subscription(
                binding.binding_id,
                state=state,
                actor_id="instagram-login-cleanup-pending",
            ),
        )
    except Exception:
        latest = next(
            (
                item
                for item in registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            None,
        )
        if (
            latest is None
            or latest.webhook_subscription_status != INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS
            or latest.webhook_subscription_error != error
            or latest.webhook_subscribed_fields != tuple(restore_target or ())
            or not registry.binding_credential_is_available(binding.binding_id)
        ):
            raise
        return latest


def _authorize_staged_instagram_binding_reconciled(
    *,
    registry: MetaAppRegistry,
    tenant_id: str,
    instagram_id: str,
    instagram_username: str,
    credential: MetaBindingCredential,
    actor_id: str,
) -> MetaAssetBinding:
    """Stage direct OAuth and clean a file/dual commit whose acknowledgement was lost."""

    before_ids = {
        item.binding_id
        for item in registry.list_bindings(include_inactive=True, include_superseded=True)
        if item.tenant_id == tenant_id
        and item.channel == "instagram"
        and item.asset_id == instagram_id
        and item.app_key == APP_A_KEY
        and item.auth_flow == "instagram_login"
    }
    try:
        return registry.authorize_oauth_asset(
            tenant_id=tenant_id,
            channel="instagram",
            asset_id=instagram_id,
            page_id="",
            instagram_account_id=instagram_id,
            app_key=APP_A_KEY,
            credential=credential,
            actor_id=actor_id,
            instagram_username=instagram_username,
            status="testing",
            auth_flow="instagram_login",
            webhook_subscription_status="pending",
            create_new_binding=True,
        )
    except Exception:
        candidates = [
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.binding_id not in before_ids
            and item.tenant_id == tenant_id
            and item.channel == "instagram"
            and item.asset_id == instagram_id
            and item.app_key == APP_A_KEY
            and item.auth_flow == "instagram_login"
            and item.status == "testing"
            and registry.binding_credential_is_available(item.binding_id)
        ]
        if len(candidates) == 1:
            _discard_staged_instagram_binding_reconciled(
                candidates[0],
                actor_id=actor_id,
                registry=registry,
            )
        raise


def _instagram_activation_commit_matches(
    latest: MetaAssetBinding | None,
    *,
    staged: MetaAssetBinding,
    registry: MetaAppRegistry,
) -> bool:
    if (
        latest is None
        or not latest.active
        or latest.binding_id != staged.binding_id
        or latest.tenant_id != staged.tenant_id
        or latest.channel != "instagram"
        or latest.asset_id != staged.asset_id
        or latest.app_key != staged.app_key
        or latest.auth_flow != "instagram_login"
        or not latest.instagram_login_product_ready
        or not registry.binding_credential_is_available(latest.binding_id)
    ):
        return False
    active = [
        item
        for item in registry.list_bindings(include_inactive=False, include_superseded=True)
        if item.channel == "instagram" and item.asset_id == staged.asset_id
    ]
    return [item.binding_id for item in active] == [latest.binding_id]


async def _compensate_failed_instagram_activation(
    binding: MetaAssetBinding,
    *,
    previous_active: MetaAssetBinding | None,
    provider_preimage: tuple[str, ...] | None,
    provider_write_started: bool,
    actor_id: str,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
) -> None:
    """Restore exact provider state before archiving a failed staged credential."""

    if provider_write_started:
        actual = await inspect_instagram_login_webhook_subscription(
            binding,
            registry=registry,
            client=client,
        )
        restore_target = (
            provider_preimage
            if previous_active is not None and previous_active.auth_flow == "instagram_login"
            else None
        )
        await restore_instagram_login_webhook_subscription(
            binding,
            restore_target,
            expected_current=actual,
            registry=registry,
            client=client,
        )
    latest = next(
        (
            item
            for item in registry.list_bindings(include_inactive=True, include_superseded=True)
            if item.binding_id == binding.binding_id
        ),
        None,
    )
    if latest is None:
        return
    if latest.active:
        raise MetaOAuthError("Instagram activation outcome is ambiguous; refusing staged cleanup")
    _discard_staged_instagram_binding_reconciled(latest, actor_id=actor_id, registry=registry)


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
                    staged = next(
                        item
                        for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                        if item.binding_id == binding.binding_id
                    )
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
