"""Instagram API with Instagram Login OAuth for Meta App A."""

from __future__ import annotations

import hashlib
import secrets
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

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
from services.meta_instagram_login_subscription import ensure_instagram_login_webhook_subscription
from services.meta_oauth import META_OAUTH_STATE_TTL_SECONDS, MetaOAuthError, _safe_json

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
            "expires_at": time.time() + META_OAUTH_STATE_TTL_SECONDS,
        },
    )
    query = urlencode(
        {
            "client_id": instagram_login_app_id(),
            "redirect_uri": instagram_login_redirect_uri(),
            "response_type": "code",
            "scope": ",".join(sorted(META_INSTAGRAM_LOGIN_REQUEST_SCOPES)),
            "state": nonce,
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
        raise MetaOAuthError("Instagram code exchange did not return a user access token")
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


async def complete_instagram_login(
    *,
    code: str,
    state: str,
    registry: MetaAppRegistry | None = None,
    client: httpx.AsyncClient | None = None,
) -> InstagramLoginOAuthResult:
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
        )
        binding = current_registry.authorize_oauth_asset(
            tenant_id=tenant_id,
            channel="instagram",
            asset_id=instagram_id,
            page_id="",
            instagram_account_id=instagram_id,
            app_key=APP_A_KEY,
            credential=credential,
            actor_id=actor_id,
            instagram_username=instagram_username,
            status="active",
            auth_flow="instagram_login",
            webhook_subscription_status="pending",
        )
        app = get_meta_app_configs()[APP_A_KEY]
        await ensure_instagram_login_webhook_subscription(
            binding,
            credential,
            registry=current_registry,
            graph_api_version=app.graph_api_version,
            client=http_client,
        )
        binding = next(
            item
            for item in current_registry.list_bindings(include_inactive=False, include_superseded=True)
            if item.binding_id == binding.binding_id
        )
        current_registry.archive_superseded_duplicate_bindings(actor_id=actor_id)
        from services.channel_capability_toggles import sync_published_comment_assets_if_enabled

        try:
            await sync_published_comment_assets_if_enabled(tenant_id=tenant_id, platform="instagram")
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
