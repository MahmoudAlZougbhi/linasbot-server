"""Server-side Facebook Login for Business onboarding for the single Meta app (App A).

OAuth codes and tokens never reach the dashboard. The callback validates a one-time
server-side state record, exchanges the code with Meta, inspects the resulting Page
token, resolves the linked professional Instagram account, and persists only an
AES-GCM encrypted credential through :mod:`services.meta_app_registry`.

Graph helpers / webhooks: meta_oauth_graph (LOC split).
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
    FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT,
    META_CHANNEL_SCOPES,
    META_COMMENT_SCOPES,
    META_FACEBOOK_LOGIN_EXTRA_SCOPES,
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
from services.meta_oauth_graph import (  # noqa: F401 — re-export Graph helpers for meta_* consumers
    META_GRAPH_BASE_URL,
    MetaOAuthError,
    _debug_token,
    _eligible_pages,
    _granular_targets_are_allowlisted,
    _graph_get,
    _graph_post_form,
    _safe_json,
    _scope_tuple,
    disconnect_binding_webhook,
    subscribe_binding_webhook,
    unsubscribe_binding_webhook,
)

MetaOAuthFlowMode = Literal["facebook", "instagram", "unified"]

META_OAUTH_STATE_TTL_SECONDS = 10 * 60

@dataclass(frozen=True)
class MetaOAuthResult:
    bindings: tuple[MetaAssetBinding, ...]
    page_name: str
    instagram_username: str
    return_surface: str = "web"

    @property
    def binding(self) -> MetaAssetBinding:
        return self.bindings[0]


def meta_oauth_redirect_uri() -> str:
    return (os.getenv("META_OAUTH_REDIRECT_URI") or "https://www.linasaibot.com/oauth/meta/callback").strip()


def meta_oauth_app_key() -> str:
    """Return the configured Meta app used for dashboard Connect (App A only)."""

    app = get_meta_app_configs()[APP_A_KEY]
    if app.enabled and (app.app_id and app.app_secret):
        return APP_A_KEY
    raise MetaOAuthError("Meta App A is not configured for Business Login")


def facebook_login_config_id() -> str:
    """Facebook Connect / Manage Meta Access uses the Facebook-Pages-only config."""

    configured = (os.getenv("META_APP_A_FACEBOOK_LOGIN_CONFIG_ID") or "").strip()
    if configured:
        return configured
    return FACEBOOK_ONLY_LOGIN_CONFIG_ID_DEFAULT


def resolve_business_login_config_id(flow_mode: MetaOAuthFlowMode) -> str:
    """Pick the Login Configuration for Facebook Business Login.

    Facebook Connect and Manage Meta Access use the Facebook-Pages-only config.
    Instagram Connect must use Instagram Login (``/instagram-login/start``), not
    Facebook Login for Business.
    """

    if flow_mode == "instagram":
        raise MetaOAuthError(
            "Instagram Connect uses Instagram Login, not Facebook Login for Business. "
            "Start via /api/meta/connections/instagram-login/start."
        )

    # ``facebook`` and legacy ``unified``/``meta`` starts both use the Pages-only config.
    config_id = facebook_login_config_id()
    if not config_id:
        raise MetaOAuthError(
            "Facebook Business Login is not configured. Ask ops to set META_APP_A_FACEBOOK_LOGIN_CONFIG_ID for App A."
        )
    return config_id


def normalize_oauth_flow_channel(channel: str) -> MetaOAuthFlowMode:
    """Normalize Connect / Manage Meta Access channel without forcing FB+IG together."""

    normalized = (channel or "unified").strip().lower()
    if normalized in {"facebook", "instagram", "unified"}:
        return cast(MetaOAuthFlowMode, normalized)
    if normalized in {"meta", ""}:
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


def _business_login_request_scopes(flow_mode: MetaOAuthFlowMode) -> str:
    """Scopes requested alongside Login Config (rerequest).

    Facebook Connect / Manage Meta Access must request only Page/DM + FB comment
    scopes (+ ``business_management``). Do not bundle any ``instagram_*``
    permissions — Instagram Connect uses the independent Instagram Login flow.
    """

    scopes: set[str] = set()
    if flow_mode == "instagram":
        # Business Login must not start Instagram Connect; scopes unused when rejected above.
        scopes |= set(META_CHANNEL_SCOPES["instagram"])
        scopes |= set(META_COMMENT_SCOPES["instagram"])
    else:
        # Facebook Connect and legacy unified starts: Pages only (no instagram_*).
        scopes |= set(META_CHANNEL_SCOPES["facebook"])
        scopes |= set(META_COMMENT_SCOPES["facebook"])
        scopes |= set(META_FACEBOOK_LOGIN_EXTRA_SCOPES)
    return ",".join(sorted(scopes))


def begin_meta_business_login(
    *,
    tenant_id: str,
    channel: str = "unified",
    actor_id: str,
    return_surface: str = "web",
    registry: MetaAppRegistry | None = None,
) -> str:
    """Create a one-time state and return App A's Business Login URL."""

    from services.meta_oauth_return import normalize_return_surface

    flow_mode = normalize_oauth_flow_channel(channel)
    app_key = meta_oauth_app_key()
    app = get_meta_app_configs()[app_key]
    config_id = resolve_business_login_config_id(flow_mode)
    try:
        tenant = normalize_meta_tenant_id(tenant_id)
    except MetaBindingConflictError as exc:
        raise MetaOAuthError("Tenant is unavailable for this session") from exc

    nonce = secrets.token_urlsafe(32)
    nonce_hash = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    actor_reference = hashlib.sha256(str(actor_id or "oauth").encode("utf-8")).hexdigest()[:16]
    surface = normalize_return_surface(return_surface)
    current_registry = registry or get_meta_app_registry()
    current_registry.store_oauth_state(
        nonce_hash,
        {
            "tenant_id": tenant,
            "channel": flow_mode,
            "actor_id": f"oauth:{actor_reference}",
            "app_key": app_key,
            "redirect_uri": meta_oauth_redirect_uri(),
            "return_surface": surface,
            "login_config_id": config_id,
            "expires_at": time.time() + META_OAUTH_STATE_TTL_SECONDS,
        },
    )
    query = urlencode(
        {
            "client_id": app.app_id,
            "redirect_uri": meta_oauth_redirect_uri(),
            "state": nonce,
            "response_type": "code",
            "config_id": config_id,
            "override_default_response_type": "true",
            # Ask Meta to re-present permissions (including comments) for the same assets.
            "auth_type": "rerequest",
            "scope": _business_login_request_scopes(flow_mode),
        }
    )
    return f"https://www.facebook.com/{app.graph_api_version}/dialog/oauth?{query}"



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
    from services.meta_oauth_return import normalize_return_surface

    return_surface = normalize_return_surface(state_data.get("return_surface"))
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
        from services.channel_capability_toggles import sync_published_comment_assets_if_enabled

        for channel in sorted({binding.channel for binding in authorized_bindings}):
            try:
                await sync_published_comment_assets_if_enabled(tenant_id=tenant_id, platform=channel)
            except Exception:
                pass
        return MetaOAuthResult(
            bindings=tuple(authorized_bindings),
            page_name=primary_page_name,
            instagram_username=primary_instagram_username,
            return_surface=return_surface,
        )
    finally:
        if owns_client:
            await http_client.aclose()


