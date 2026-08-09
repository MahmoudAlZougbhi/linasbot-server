"""Server-side Facebook Login for Business onboarding for the single Meta app (App A).

OAuth codes and tokens never reach the dashboard. The callback validates a one-time
server-side state record, exchanges the code with Meta, inspects the resulting Page
token, resolves the linked professional Instagram account, and persists only an
AES-GCM encrypted credential through :mod:`services.meta_app_registry`.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal, cast
from urllib.parse import urlencode

import httpx

from services.meta_app_registry import (
    APP_A_KEY,
    META_CHANNEL_SCOPES,
    META_FORBIDDEN_SCOPES,
    MetaAppRegistry,
    MetaAssetBinding,
    MetaBindingConflictError,
    MetaBindingCredential,
    MetaChannel,
    MetaOAuthStateError,
    get_meta_app_configs,
    get_meta_app_registry,
    normalize_meta_tenant_id,
)

MetaOAuthFlowMode = Literal["facebook", "instagram", "unified"]

META_OAUTH_STATE_TTL_SECONDS = 10 * 60
META_GRAPH_BASE_URL = "https://graph.facebook.com"


class MetaOAuthError(RuntimeError):
    """OAuth failure whose message never contains a secret or raw Meta response."""


@dataclass(frozen=True)
class MetaOAuthResult:
    bindings: tuple[MetaAssetBinding, ...]
    page_name: str
    instagram_username: str

    @property
    def binding(self) -> MetaAssetBinding:
        return self.bindings[0]


def meta_oauth_redirect_uri() -> str:
    return (os.getenv("META_OAUTH_REDIRECT_URI") or "https://www.linasaibot.com/oauth/meta/callback").strip()


def meta_oauth_app_key() -> str:
    """Return the configured Meta app used for dashboard Connect (App A only)."""

    app = get_meta_app_configs()[APP_A_KEY]
    if app.enabled and app.oauth_config_id:
        return APP_A_KEY
    raise MetaOAuthError("Meta Business Login is not configured. Ask ops to set META_APP_A_LOGIN_CONFIG_ID for App A.")


def normalize_oauth_flow_channel(channel: str) -> MetaOAuthFlowMode:
    """Map dashboard connect requests to the unified Business Login flow."""

    normalized = (channel or "unified").strip().lower()
    if normalized in {"unified", "meta", "facebook", "instagram", ""}:
        return "unified"
    raise MetaOAuthError("Unsupported Meta channel")


def _resolve_oauth_flow_channel(state_channel: str) -> MetaOAuthFlowMode:
    normalized = (state_channel or "").strip().lower()
    if normalized in {"facebook", "instagram", "unified"}:
        return cast(MetaOAuthFlowMode, normalized)
    raise MetaOAuthStateError("OAuth state binding is invalid")


def _channels_for_authorization(
    *,
    flow_mode: MetaOAuthFlowMode,
    scopes: tuple[str, ...],
    instagram_id: str,
) -> tuple[MetaChannel, ...]:
    if flow_mode == "facebook":
        return ("facebook",)
    if flow_mode == "instagram":
        return ("instagram",)
    channels: list[MetaChannel] = []
    if META_CHANNEL_SCOPES["facebook"].issubset(scopes):
        channels.append("facebook")
    if instagram_id and META_CHANNEL_SCOPES["instagram"].issubset(scopes):
        channels.append("instagram")
    return tuple(channels)


def begin_meta_business_login(
    *,
    tenant_id: str,
    channel: str = "unified",
    actor_id: str,
    registry: MetaAppRegistry | None = None,
) -> str:
    """Create a one-time state and return App A's Business Login URL."""

    flow_mode = normalize_oauth_flow_channel(channel)
    app_key = meta_oauth_app_key()
    app = get_meta_app_configs()[app_key]
    try:
        tenant = normalize_meta_tenant_id(tenant_id)
    except MetaBindingConflictError as exc:
        raise MetaOAuthError("Tenant is unavailable for this session") from exc

    nonce = secrets.token_urlsafe(32)
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    actor_reference = hashlib.sha256(str(actor_id or "oauth").encode("utf-8")).hexdigest()[:16]
    current_registry = registry or get_meta_app_registry()
    current_registry.store_oauth_state(
        nonce_hash,
        {
            "tenant_id": tenant,
            "channel": flow_mode,
            "actor_id": f"oauth:{actor_reference}",
            "app_key": app_key,
            "redirect_uri": meta_oauth_redirect_uri(),
            "expires_at": time.time() + META_OAUTH_STATE_TTL_SECONDS,
        },
    )
    query = urlencode(
        {
            "client_id": app.app_id,
            "redirect_uri": meta_oauth_redirect_uri(),
            "state": nonce,
            "response_type": "code",
            "config_id": app.oauth_config_id,
            "override_default_response_type": "true",
        }
    )
    return f"https://www.facebook.com/{app.graph_api_version}/dialog/oauth?{query}"


def _safe_json(response: httpx.Response, *, step: str) -> dict[str, Any]:
    if response.status_code < 200 or response.status_code >= 300:
        raise MetaOAuthError(f"Meta {step} failed with HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MetaOAuthError(f"Meta {step} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise MetaOAuthError(f"Meta {step} returned an invalid response")
    if payload.get("error"):
        raise MetaOAuthError(f"Meta {step} returned an OAuth error")
    return cast(dict[str, Any], payload)


async def _graph_get(
    client: httpx.AsyncClient,
    path: str,
    *,
    step: str,
    params: dict[str, str],
    bearer_token: str = "",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    try:
        response = await client.get(path, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise MetaOAuthError(f"Meta {step} request failed") from exc
    return _safe_json(response, step=step)


async def _graph_post_form(
    client: httpx.AsyncClient,
    path: str,
    *,
    step: str,
    data: dict[str, str],
    bearer_token: str = "",
) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {bearer_token}"} if bearer_token else {}
    try:
        response = await client.post(path, data=data, headers=headers)
    except httpx.HTTPError as exc:
        raise MetaOAuthError(f"Meta {step} request failed") from exc
    return _safe_json(response, step=step)


async def _debug_token(
    client: httpx.AsyncClient,
    *,
    token: str,
    app_id: str,
    app_secret: str,
) -> dict[str, Any]:
    payload = await _graph_get(
        client,
        "debug_token",
        step="token inspection",
        params={"input_token": token},
        bearer_token=f"{app_id}|{app_secret}",
    )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MetaOAuthError("Meta token inspection response is incomplete")
    if not data.get("is_valid") or str(data.get("app_id") or "") != app_id:
        raise MetaOAuthError("Meta token does not belong to the Tech Provider app")
    return cast(dict[str, Any], data)


def _scope_tuple(debug_data: dict[str, Any]) -> tuple[str, ...]:
    scopes = debug_data.get("scopes")
    if not isinstance(scopes, list):
        return ()
    return tuple(sorted({str(scope) for scope in scopes if str(scope).strip()}))


def _granular_targets_are_allowlisted(
    debug_data: dict[str, Any],
    *,
    page_id: str,
    instagram_id: str,
) -> bool:
    granular = debug_data.get("granular_scopes")
    if not isinstance(granular, list):
        return False
    allowed_targets = {page_id}
    if instagram_id:
        allowed_targets.add(instagram_id)
    observed_targets: set[str] = set()
    relevant = [
        item
        for item in granular
        if isinstance(item, dict) and str(item.get("scope") or "") in META_CHANNEL_SCOPES["facebook"]
    ]
    for item in relevant:
        targets = item.get("target_ids")
        if not isinstance(targets, list) or not targets:
            continue
        normalized = {str(value) for value in targets}
        if not normalized.issubset(allowed_targets):
            return False
        observed_targets.update(normalized)
    return page_id in observed_targets


def _eligible_pages(pages: list[dict[str, Any]], *, flow_mode: MetaOAuthFlowMode) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page in pages:
        page_id = str(page.get("id") or "").strip()
        page_token = str(page.get("access_token") or "").strip()
        instagram = page.get("instagram_business_account")
        if not page_id or not page_token:
            continue
        if flow_mode == "instagram" and not isinstance(instagram, dict):
            continue
        candidates.append(page)
    if not candidates:
        raise MetaOAuthError("No eligible Facebook Page was authorized in Meta Business Login")
    return candidates


async def complete_meta_business_login(
    *,
    code: str,
    state: str,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> MetaOAuthResult:
    """Validate code/state, inspect assets, and create one exclusive binding."""

    if not code or not state:
        raise MetaOAuthStateError("OAuth code and state are required")
    current_registry = registry or get_meta_app_registry()
    state_hash = hashlib.sha256(state.encode("utf-8")).hexdigest()
    state_data = current_registry.consume_oauth_state(state_hash)
    if state_data.get("app_key") != APP_A_KEY:
        raise MetaOAuthStateError("OAuth state app does not match")
    redirect_uri = str(state_data.get("redirect_uri") or "")
    if redirect_uri != meta_oauth_redirect_uri():
        raise MetaOAuthStateError("OAuth redirect does not match")
    tenant_id = str(state_data.get("tenant_id") or "").strip()
    flow_mode = _resolve_oauth_flow_channel(str(state_data.get("channel") or ""))
    actor_id = str(state_data.get("actor_id") or "oauth")
    if not tenant_id:
        raise MetaOAuthStateError("OAuth state binding is invalid")

    app_key = meta_oauth_app_key()
    app = get_meta_app_configs()[app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}",
        timeout=20.0,
        follow_redirects=False,
    )
    try:
        exchange = await _graph_post_form(
            http_client,
            "oauth/access_token",
            step="authorization-code exchange",
            data={
                "client_id": app.app_id,
                "client_secret": app.app_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        integration_token = str(exchange.get("access_token") or "")
        if not integration_token:
            raise MetaOAuthError("Meta code exchange did not return an access token")
        integration_debug = await _debug_token(
            http_client,
            token=integration_token,
            app_id=app.app_id,
            app_secret=app.app_secret,
        )
        authorized_meta_user_id = str(integration_debug.get("user_id") or "").strip()
        if not authorized_meta_user_id.isdigit() or not 3 <= len(authorized_meta_user_id) <= 64:
            raise MetaOAuthError("Meta authorization owner is missing from the inspected token")

        pages_payload = await _graph_get(
            http_client,
            "me/accounts",
            step="Page discovery",
            params={
                "fields": "id,name,access_token,tasks,instagram_business_account{id,username}",
                "limit": "100",
            },
            bearer_token=integration_token,
        )
        raw_pages = pages_payload.get("data")
        if not isinstance(raw_pages, list):
            raise MetaOAuthError("Meta Page discovery response is incomplete")
        pages = [cast(dict[str, Any], page) for page in raw_pages if isinstance(page, dict)]
        selected_pages = _eligible_pages(pages, flow_mode=flow_mode)
        authorized_bindings: list[MetaAssetBinding] = []
        primary_page_name = ""
        primary_instagram_username = ""
        for selected in selected_pages:
            page_id = str(selected.get("id") or "")
            page_name = str(selected.get("name") or "Facebook Page")
            page_token = str(selected.get("access_token") or "")
            instagram = selected.get("instagram_business_account")
            instagram_id = str(instagram.get("id") or "") if isinstance(instagram, dict) else ""
            instagram_username = str(instagram.get("username") or "") if isinstance(instagram, dict) else ""

            page_debug = await _debug_token(
                http_client,
                token=page_token,
                app_id=app.app_id,
                app_secret=app.app_secret,
            )
            if str(page_debug.get("profile_id") or "") != page_id:
                raise MetaOAuthError("Meta Page token profile does not match the selected Page")
            if str(page_debug.get("type") or "").upper() != "PAGE":
                raise MetaOAuthError("Meta token is not a Page access token")
            scopes = _scope_tuple(page_debug) or _scope_tuple(integration_debug)
            if set(scopes) & META_FORBIDDEN_SCOPES:
                raise MetaOAuthError("Meta token includes a prohibited non-messaging permission")
            if flow_mode == "instagram" and not instagram_id:
                raise MetaOAuthError("The selected Page has no linked professional Instagram account")
            if not _granular_targets_are_allowlisted(
                page_debug,
                page_id=page_id,
                instagram_id=instagram_id,
            ):
                continue

            channels_to_authorize = _channels_for_authorization(
                flow_mode=flow_mode,
                scopes=scopes,
                instagram_id=instagram_id,
            )
            if flow_mode in {"facebook", "instagram"}:
                required = META_CHANNEL_SCOPES[flow_mode]
                if not required.issubset(scopes):
                    raise MetaOAuthError("Meta token is missing required private-messaging permissions")
            elif not channels_to_authorize:
                continue

            credential = MetaBindingCredential(
                access_token=page_token,
                token_app_id=app.app_id,
                token_profile_id=page_id,
                scopes=scopes,
                expires_at=int(page_debug["expires_at"]) if page_debug.get("expires_at") else None,
                authorized_meta_user_id=authorized_meta_user_id,
            )
            subscribed = False
            for authorize_channel in channels_to_authorize:
                if authorize_channel == "instagram" and not instagram_id:
                    continue
                asset_id = page_id if authorize_channel == "facebook" else instagram_id
                binding = current_registry.authorize_oauth_asset(
                    tenant_id=tenant_id,
                    channel=authorize_channel,
                    asset_id=asset_id,
                    page_id=page_id,
                    instagram_account_id=instagram_id,
                    app_key=app_key,
                    credential=credential,
                    actor_id=actor_id,
                    page_name=page_name,
                    instagram_username=instagram_username,
                    status="active",
                )
                authorized_bindings.append(binding)
                if not subscribed:
                    await subscribe_binding_webhook(binding, registry=current_registry, client=client)
                    subscribed = True
                if not primary_page_name:
                    primary_page_name = page_name
                    primary_instagram_username = instagram_username

        if not authorized_bindings:
            raise MetaOAuthError("Meta token granular targets are missing or include another asset")
        current_registry.archive_superseded_duplicate_bindings(actor_id=actor_id)
        return MetaOAuthResult(
            bindings=tuple(authorized_bindings),
            page_name=primary_page_name,
            instagram_username=primary_instagram_username,
        )
    finally:
        if owns_client:
            await http_client.aclose()


async def subscribe_binding_webhook(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Subscribe only private-message webhook fields for an active binding."""

    if not binding.active:
        raise MetaOAuthError("Only an active binding may subscribe webhooks")
    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    try:
        response = await http_client.post(
            f"{binding.page_id}/subscribed_apps",
            data={"subscribed_fields": "messages,messaging_postbacks"},
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        _safe_json(response, step="webhook subscription")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta webhook subscription request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()


async def disconnect_binding_webhook(
    binding: MetaAssetBinding,
    *,
    actor_id: str,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> MetaAssetBinding:
    """Unsubscribe the Page, then retain an encrypted disconnected rollback record."""

    current_registry = registry or get_meta_app_registry()
    if binding.auth_flow != "instagram_login" and binding.page_id:
        await unsubscribe_binding_webhook(binding, registry=current_registry, client=client)
    return current_registry.set_binding_status(
        binding.binding_id,
        status="disconnected",
        actor_id=actor_id,
        expected_generation=binding.generation,
    )


async def unsubscribe_binding_webhook(
    binding: MetaAssetBinding,
    *,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> None:
    """Remove only this app's Page webhook subscription without mutating registry state."""

    current_registry = registry or get_meta_app_registry()
    credential = current_registry.get_credential(binding)
    app = get_meta_app_configs()[binding.app_key]
    owns_client = client is None
    http_client = client or httpx.AsyncClient(base_url=f"{META_GRAPH_BASE_URL}/{app.graph_api_version}", timeout=20.0)
    try:
        response = await http_client.delete(
            f"{binding.page_id}/subscribed_apps",
            headers={"Authorization": f"Bearer {credential.access_token}"},
        )
        _safe_json(response, step="webhook disconnect")
    except httpx.HTTPError as exc:
        raise MetaOAuthError("Meta webhook disconnect request failed") from exc
    finally:
        if owns_client:
            await http_client.aclose()
