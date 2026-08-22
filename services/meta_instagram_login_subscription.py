"""Instagram Login per-account webhook subscription via graph.instagram.com."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from services.meta_app_registry import (
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingCredential,
    get_meta_app_configs,
    get_meta_app_registry,
)
from services.meta_instagram_login_config import META_INSTAGRAM_GRAPH_BASE_URL, instagram_login_app_id
from services.meta_instagram_login_subscription_telemetry import (
    extract_instagram_subscribed_apps_telemetry,
    log_instagram_subscribed_apps_telemetry,
)
from services.meta_oauth_graph_http import MetaOAuthError, _safe_json
from services.meta_oauth_page_lock import lock_facebook_page_oauth_operation

_runtime_logger = logging.getLogger("uvicorn.error")

REQUIRED_DM_SUBSCRIPTION_FIELDS = frozenset({"messages", "messaging_postbacks"})
COMMENTS_SUBSCRIPTION_FIELD = "comments"
InstagramLoginWebhookSubscriptionSnapshot = tuple[str, ...] | None
INSTAGRAM_LOGIN_CLEANUP_PENDING_STATUS = "cleanup_pending"
INSTAGRAM_LOGIN_CLEANUP_DELETE_ERROR = "cleanup_delete_subscription"
INSTAGRAM_LOGIN_CLEANUP_RESTORE_ERROR = "cleanup_restore_preimage"
INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR = "verification_rate_limited"
INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR = "verification_deferred"
INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR = "subscription_write_rejected"
_VERIFY_BACKOFF_SECONDS = (0.0, 2.0, 5.0)


class _InstagramSubscribedAppsProviderError(MetaOAuthError):
    """Secret-safe provider response classification for one subscribed_apps call."""

    def __init__(self, message: str, *, rate_limited: bool, retryable: bool) -> None:
        super().__init__(message)
        self.rate_limited = rate_limited
        self.retryable = retryable


def _raise_classified_provider_error(response: httpx.Response, *, step: str) -> None:
    """Raise a fixed-message error for a non-success provider response."""

    safe = extract_instagram_subscribed_apps_telemetry(response)
    rate_limited = response.status_code == 429 or safe["error_code"] == "613"
    provider_error = bool(safe["error_type"] or safe["error_code"])
    if 200 <= response.status_code < 300 and not provider_error:
        return
    if rate_limited:
        message = (
            "Instagram provider is temporarily limiting webhook subscription verification. "
            "Wait a few minutes, then tap Connect once."
        )
    else:
        message = (
            f"Meta {step} returned an OAuth error"
            if 200 <= response.status_code < 300
            else f"Meta {step} failed with HTTP {response.status_code}"
        )
    raise _InstagramSubscribedAppsProviderError(
        message,
        rate_limited=rate_limited,
        retryable=rate_limited or response.status_code >= 500 or safe["is_transient"] == "true",
    )


def instagram_login_subscription_lock_asset(ig_user_id: str) -> str:
    """Return the durable writer-lock identity shared by connect and disconnect."""

    normalized = str(ig_user_id or "").strip()
    if not normalized.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")
    return f"instagram-login:{normalized}"


def instagram_channel_subscription_lock_asset(tenant_id: str) -> str:
    """Serialize tenant-wide Instagram connect/disconnect target-set changes."""

    normalized = str(tenant_id or "").strip().lower()
    if not normalized:
        raise MetaOAuthError("Instagram workspace lock identity is invalid")
    return f"instagram-channel:{normalized}"


@dataclass(frozen=True)
class InstagramLoginSubscriptionState:
    status: str
    subscribed_fields: tuple[str, ...]
    verified_fields: tuple[str, ...]
    error: str = ""

    @property
    def ready_for_dm(self) -> bool:
        return REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(self.verified_fields)

    @property
    def ready_for_comments(self) -> bool:
        return COMMENTS_SUBSCRIPTION_FIELD in self.verified_fields

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "subscribed_fields": list(self.subscribed_fields),
            "verified_fields": list(self.verified_fields),
            "ready_for_dm": self.ready_for_dm,
            "ready_for_comments": self.ready_for_comments,
            "error": self.error,
        }


def subscribed_fields_for_granted_scopes(scopes: tuple[str, ...] | frozenset[str]) -> tuple[str, ...]:
    granted = set(scopes)
    fields = ["messages", "messaging_postbacks"]
    if "instagram_business_manage_comments" in granted:
        fields.append(COMMENTS_SUBSCRIPTION_FIELD)
    return tuple(fields)


def _subscription_status_for_verified(*, verified: frozenset[str], subscribed_fields: tuple[str, ...]) -> str:
    if not REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(verified):
        return "failed"
    if COMMENTS_SUBSCRIPTION_FIELD in subscribed_fields and COMMENTS_SUBSCRIPTION_FIELD not in verified:
        return "partial"
    return "ready"


def _parse_verified_fields(payload: dict[str, Any], *, expected_app_id: str) -> frozenset[str]:
    """Return fields only from the one direct-Instagram app subscription row."""

    rows = payload.get("data")
    matching = [
        row
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict) and str(row.get("id") or "").strip() == expected_app_id
    ]
    if len(matching) != 1:
        return frozenset()
    subscribed_fields = matching[0].get("subscribed_fields")
    verified: set[str] = set()
    if isinstance(subscribed_fields, list):
        verified.update(str(item).strip() for item in subscribed_fields if str(item).strip())
    if isinstance(subscribed_fields, str):
        verified.update(item.strip() for item in subscribed_fields.split(",") if item.strip())
    return frozenset(verified)


def _parse_subscription_snapshot(
    payload: dict[str, Any],
    *,
    expected_app_id: str,
) -> InstagramLoginWebhookSubscriptionSnapshot:
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise MetaOAuthError("Instagram webhook subscription rows could not be verified")
    matching = [row for row in rows if isinstance(row, dict) and str(row.get("id") or "").strip() == expected_app_id]
    if len(matching) > 1:
        raise MetaOAuthError("Instagram webhook subscription rows are ambiguous")
    if not matching:
        return None
    raw_fields = matching[0].get("subscribed_fields")
    if isinstance(raw_fields, list):
        fields = {str(item).strip() for item in raw_fields if str(item).strip()}
    elif isinstance(raw_fields, str):
        fields = {item.strip() for item in raw_fields.split(",") if item.strip()}
    else:
        raise MetaOAuthError("Instagram webhook subscription fields could not be verified")
    return tuple(sorted(fields))


def _instagram_login_subscription_context(
    binding: MetaAssetBinding,
    registry: MetaAppRegistry,
) -> tuple[MetaBindingCredential, str, str]:
    if binding.channel != "instagram" or binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Instagram Login subscription requires a direct Instagram binding")
    ig_user_id = str(binding.asset_id or "").strip()
    if not ig_user_id.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")
    credential = registry.get_credential(binding)
    expected_app_id = instagram_login_app_id()
    if credential.token_app_id != expected_app_id:
        raise MetaOAuthError("Instagram Login credential belongs to an unexpected app")
    if credential.token_profile_id != ig_user_id:
        raise MetaOAuthError("Instagram Login credential does not match the professional account")
    app = get_meta_app_configs().get(binding.app_key)
    if app is None or not app.enabled or not app.graph_api_version:
        raise MetaOAuthError("Instagram Login Graph version is unavailable")
    return credential, app.graph_api_version, expected_app_id


async def _read_instagram_login_subscription(
    *,
    ig_user_id: str,
    access_token: str,
    graph_api_version: str,
    expected_app_id: str,
    client: httpx.AsyncClient,
    step: str,
    telemetry_stage: str | None = None,
) -> InstagramLoginWebhookSubscriptionSnapshot:
    response = await client.get(
        f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}/{ig_user_id}/subscribed_apps",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if telemetry_stage is not None:
        log_instagram_subscribed_apps_telemetry(response, stage=telemetry_stage)
    _raise_classified_provider_error(response, step=step)
    payload = _safe_json(response, step=step)
    return _parse_subscription_snapshot(payload, expected_app_id=expected_app_id)


async def inspect_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginWebhookSubscriptionSnapshot:
    """Read this direct Instagram app/account subscription without exposing its token."""

    credential, graph_api_version, expected_app_id = _instagram_login_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        return await _read_instagram_login_subscription(
            ig_user_id=binding.asset_id,
            access_token=credential.access_token,
            graph_api_version=graph_api_version,
            expected_app_id=expected_app_id,
            client=http_client,
            step="instagram subscribed_apps disconnect preflight",
        )
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram webhook subscription inspection failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def unsubscribe_instagram_login_webhook_raw(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Delete one direct Instagram subscription after the caller serializes writers."""

    credential, graph_api_version, _expected_app_id = _instagram_login_subscription_context(binding, registry)
    owns_client = client is None
    http_client = client or httpx.AsyncClient(timeout=20.0)
    try:
        response = await http_client.delete(
            f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}/{binding.asset_id}/subscribed_apps",
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        payload = _safe_json(response, step="instagram subscribed_apps disconnect")
        if payload.get("success") is not True:
            raise MetaOAuthError("Instagram webhook disconnect did not return success")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram webhook disconnect request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def restore_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    snapshot: InstagramLoginWebhookSubscriptionSnapshot,
    *,
    expected_current: InstagramLoginWebhookSubscriptionSnapshot,
    registry: MetaAppRegistry,
    client: httpx.AsyncClient,
) -> None:
    """Restore direct Instagram provider state only when our delete still owns it."""

    credential, graph_api_version, expected_app_id = _instagram_login_subscription_context(binding, registry)
    current = await _read_instagram_login_subscription(
        ig_user_id=binding.asset_id,
        access_token=credential.access_token,
        graph_api_version=graph_api_version,
        expected_app_id=expected_app_id,
        client=client,
        step="instagram subscribed_apps compensation ownership check",
    )
    if current == snapshot:
        return
    if current != expected_current:
        raise MetaOAuthError("Instagram webhook subscription changed; refusing stale compensation")
    mutation_error: BaseException | None = None
    try:
        if snapshot is None:
            await unsubscribe_instagram_login_webhook_raw(binding, registry=registry, client=client)
        else:
            await _subscribe_once(
                ig_user_id=binding.asset_id,
                access_token=credential.access_token,
                subscribed_fields=snapshot,
                graph_api_version=graph_api_version,
                client=client,
            )
    except BaseException as exc:  # noqa: BLE001 - verify whether the provider committed before raising
        mutation_error = exc
    try:
        verified = await _read_instagram_login_subscription(
            ig_user_id=binding.asset_id,
            access_token=credential.access_token,
            graph_api_version=graph_api_version,
            expected_app_id=expected_app_id,
            client=client,
            step="instagram subscribed_apps compensation verification",
        )
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Instagram webhook subscription compensation request failed") from exc
    if verified == snapshot:
        return
    if mutation_error is not None:
        raise mutation_error
    raise MetaOAuthError("Instagram webhook subscription compensation could not be verified")


async def _subscribe_once(
    *,
    ig_user_id: str,
    access_token: str,
    subscribed_fields: tuple[str, ...],
    graph_api_version: str,
    client: httpx.AsyncClient,
) -> None:
    response = await client.post(
        f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}/{ig_user_id}/subscribed_apps",
        json={"subscribed_fields": list(subscribed_fields)},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    log_instagram_subscribed_apps_telemetry(response, stage="subscribe", require_success_flag=True)
    _raise_classified_provider_error(response, step="instagram subscribed_apps subscribe")
    try:
        payload = _safe_json(response, step="instagram subscribed_apps subscribe")
    except MetaOAuthError as exc:
        # A 2xx response with a missing/malformed acknowledgement can still
        # have committed. Classify it as uncertain so the caller verifies with
        # reads instead of issuing a second mutation or discarding authority.
        raise _InstagramSubscribedAppsProviderError(
            "Meta instagram subscribed_apps subscribe returned an invalid acknowledgement",
            rate_limited=False,
            retryable=True,
        ) from exc
    success = payload.get("success")
    if success is False:
        raise MetaOAuthError("Instagram webhook subscription did not return success")
    if success is not True:
        # Meta can commit the write while omitting or mistyping its success
        # acknowledgement. Preserve authority and verify with GET-only reads.
        raise _InstagramSubscribedAppsProviderError(
            "Meta instagram subscribed_apps subscribe returned an incomplete acknowledgement",
            rate_limited=False,
            retryable=True,
        )


async def _fetch_subscription_state(
    *,
    ig_user_id: str,
    access_token: str,
    graph_api_version: str,
    expected_app_id: str,
    client: httpx.AsyncClient,
) -> frozenset[str]:
    snapshot = await _read_instagram_login_subscription(
        ig_user_id=ig_user_id,
        access_token=access_token,
        graph_api_version=graph_api_version,
        expected_app_id=expected_app_id,
        client=client,
        step="instagram subscribed_apps verify",
        telemetry_stage="verify",
    )
    return frozenset(snapshot or ())


async def ensure_instagram_login_webhook_subscription(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    registry: MetaAppRegistry | None = None,
    graph_api_version: str,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginSubscriptionState:
    """Idempotently subscribe and verify webhook fields for one IG professional account."""

    if binding.auth_flow != "instagram_login":
        raise MetaOAuthError("Webhook subscription applies only to Instagram Login bindings")
    ig_user_id = binding.asset_id.strip()
    if not ig_user_id.isdigit():
        raise MetaOAuthError("Instagram professional account id is invalid")

    subscribed_fields = subscribed_fields_for_granted_scopes(credential.scopes)
    expected_app_id = instagram_login_app_id()
    if credential.token_app_id != expected_app_id:
        raise MetaOAuthError("Instagram Login credential belongs to an unexpected app")
    current_registry = registry or get_meta_app_registry()
    async with lock_facebook_page_oauth_operation(
        current_registry,
        app_key=binding.app_key,
        page_ids=(
            instagram_channel_subscription_lock_asset(binding.tenant_id),
            instagram_login_subscription_lock_asset(ig_user_id),
        ),
    ):
        latest = next(
            (
                item
                for item in current_registry.list_bindings(include_inactive=True, include_superseded=True)
                if item.binding_id == binding.binding_id
            ),
            None,
        )
        if (
            latest is None
            or latest.channel != "instagram"
            or latest.auth_flow != "instagram_login"
            or latest.asset_id != binding.asset_id
            or latest.app_key != binding.app_key
            or latest.generation != binding.generation
            or latest.status not in {"active", "testing"}
            or not current_registry.binding_credential_is_available(binding.binding_id)
        ):
            raise MetaOAuthError("Instagram Login binding changed before webhook subscription")
        return await _ensure_instagram_login_webhook_subscription_locked(
            latest,
            credential,
            registry=current_registry,
            graph_api_version=graph_api_version,
            subscribed_fields=subscribed_fields,
            expected_app_id=expected_app_id,
            client=client,
        )


async def _ensure_instagram_login_webhook_subscription_locked(
    binding: MetaAssetBinding,
    credential: MetaBindingCredential,
    *,
    registry: MetaAppRegistry,
    graph_api_version: str,
    subscribed_fields: tuple[str, ...],
    expected_app_id: str,
    client: httpx.AsyncClient | None,
) -> InstagramLoginSubscriptionState:
    """Subscribe while the caller owns the direct app/account writer lock."""

    ig_user_id = binding.asset_id.strip()
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"{META_INSTAGRAM_GRAPH_BASE_URL}/{graph_api_version}",
        timeout=20.0,
    )
    last_error = ""

    latest_verified = (
        frozenset(binding.webhook_subscribed_fields)
        if binding.active and binding.webhook_subscription_status in {"ready", "partial"}
        else frozenset[str]()
    )

    def persist_unresolved(error: str) -> InstagramLoginSubscriptionState:
        status = (
            _subscription_status_for_verified(
                verified=latest_verified,
                subscribed_fields=subscribed_fields,
            )
            if REQUIRED_DM_SUBSCRIPTION_FIELDS.issubset(latest_verified)
            else "failed"
        )
        unresolved = InstagramLoginSubscriptionState(
            status=status,
            subscribed_fields=subscribed_fields,
            verified_fields=tuple(sorted(latest_verified)),
            error=error or "subscription_verify_failed",
        )
        registry.update_instagram_login_webhook_subscription(
            binding.binding_id,
            state=unresolved,
            actor_id="instagram-login-subscribe",
        )
        return unresolved

    try:
        try:
            # One OAuth completion performs at most one provider mutation. A
            # write timeout/5xx can still have committed, so verification below
            # is GET-only and may prove that uncertain outcome successful.
            await _subscribe_once(
                ig_user_id=ig_user_id,
                access_token=credential.access_token,
                subscribed_fields=subscribed_fields,
                graph_api_version=graph_api_version,
                client=http_client,
            )
        except _InstagramSubscribedAppsProviderError as exc:
            last_error = "subscription_write_rate_limited" if exc.rate_limited else "subscription_write_failed"
            _runtime_logger.warning(
                "[instagram-login] subscribe_write_failed binding=%s reason=%s",
                binding.binding_id[-8:],
                last_error,
            )
            if exc.rate_limited:
                return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR)
            if not exc.retryable:
                return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR)
        except httpx.HTTPError:
            # Transport loss leaves the POST outcome unknown; verify without
            # issuing another write.
            last_error = "subscription_write_outcome_unknown"
        except MetaOAuthError:
            return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_WRITE_REJECTED_ERROR)

        for attempt, delay in enumerate(_VERIFY_BACKOFF_SECONDS, start=1):
            if delay:
                await asyncio.sleep(delay)
            try:
                verified = await _fetch_subscription_state(
                    ig_user_id=ig_user_id,
                    access_token=credential.access_token,
                    graph_api_version=graph_api_version,
                    expected_app_id=expected_app_id,
                    client=http_client,
                )
                latest_verified = verified
                if set(subscribed_fields).issubset(verified):
                    status = _subscription_status_for_verified(
                        verified=verified,
                        subscribed_fields=subscribed_fields,
                    )
                    state = InstagramLoginSubscriptionState(
                        status=status,
                        subscribed_fields=subscribed_fields,
                        verified_fields=tuple(sorted(verified)),
                    )
                    registry.update_instagram_login_webhook_subscription(
                        binding.binding_id,
                        state=state,
                        actor_id="instagram-login-subscribe",
                    )
                    return state
                last_error = "required_dm_fields_missing_after_verify"
            except _InstagramSubscribedAppsProviderError as exc:
                last_error = (
                    INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR
                    if exc.rate_limited
                    else "subscription_verify_provider_error"
                )
                _runtime_logger.warning(
                    "[instagram-login] subscribe_verify_failed binding=%s attempt=%d reason=%s",
                    binding.binding_id[-8:],
                    attempt,
                    last_error,
                )
                if exc.rate_limited:
                    return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_RATE_LIMITED_ERROR)
                if not exc.retryable:
                    break
            except httpx.HTTPError:
                last_error = "subscription_verify_transport_error"
            except MetaOAuthError:
                # A successful response that is incomplete or not yet valid may
                # converge; retry only the read within the fixed callback budget.
                last_error = "subscription_verify_invalid_response"

        # The single POST was accepted or its result was ambiguous. Retain the
        # staged credential so the distributed lifecycle can inspect and
        # restore/delete the provider state without issuing hot repeated writes.
        return persist_unresolved(INSTAGRAM_LOGIN_SUBSCRIPTION_DEFERRED_ERROR)
    finally:
        if owns_client:
            await http_client.aclose()
