"""TikTok Marketing API OAuth. Never overwrites the account-holder credential."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from services.meta_oauth_return import oauth_completion_redirect_url
from services.tiktok_business.ads_config import require_tiktok_ads_settings
from services.tiktok_business.capability_probe import probe_enhanced_capabilities
from services.tiktok_business.config import TOKEN_REFRESH_SKEW_SECONDS, parse_scope_string
from services.tiktok_business.errors import TikTokApiError, TikTokBusinessError, TikTokOAuthStateError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.oauth_state import create_signed_state, parse_signed_state
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository


def _expires(seconds: Any) -> datetime:
    try:
        value = int(seconds or 0)
    except (TypeError, ValueError):
        value = 0
    return datetime.now(UTC) + timedelta(seconds=max(value, 0))


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def exchange_ads_auth_code(*, auth_code: str) -> dict[str, Any]:
    settings = require_tiktok_ads_settings()
    return await tiktok_request(
        method="POST",
        path="/oauth2/access_token/",
        json_body={"app_id": settings.app_id, "secret": settings.secret, "auth_code": auth_code},
    )


async def refresh_ads_access_token(*, refresh_token: str) -> dict[str, Any]:
    settings = require_tiktok_ads_settings()
    return await tiktok_request(
        method="POST",
        path="/oauth2/refresh_token/",
        json_body={
            "app_id": settings.app_id,
            "secret": settings.secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )


async def revoke_ads_access_token(*, access_token: str) -> None:
    settings = require_tiktok_ads_settings()
    await tiktok_request(
        method="POST",
        path="/oauth2/revoke/",
        json_body={"app_id": settings.app_id, "secret": settings.secret, "access_token": access_token},
    )


def start_tiktok_ads_oauth(*, tenant_id: str, actor_user_id: str, return_surface: str = "mobile") -> dict[str, Any]:
    require_tiktok_ads_settings()
    from services.tiktok_business.entitlement import assert_tiktok_plan_allowed

    assert_tiktok_plan_allowed(tenant_id)
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.get_active_for_tenant(tenant_id)
        if connection is None or connection.lifecycle_status not in {"connected", "permission_required"}:
            raise TikTokBusinessError(
                "Connect TikTok first, then enable Enhanced Video Context.",
                code="TIKTOK_CONNECT_REQUIRED",
                http_status=409,
            )
        signed = create_signed_state(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            return_surface=return_surface,
            flow="advertiser",
        )
        surface = return_surface if return_surface in {"mobile", "web"} else "web"
        repo.create_attempt(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            return_surface=surface,
            state_hash=signed.state_hash,
            expires_at=datetime.fromtimestamp(signed.expires_at_unix, tz=UTC),
        )
        repo.audit(
            tenant_id=tenant_id,
            connection_id=connection.id,
            actor=actor_user_id,
            event="enhanced_oauth_start",
        )
        session.commit()
    settings = require_tiktok_ads_settings()
    query = urlencode(
        {
            "app_id": settings.app_id,
            "redirect_uri": settings.redirect_uri,
            "state": signed.state,
        }
    )
    return {
        "success": True,
        "authorization_url": f"{settings.authorize_url}?{query}",
        "redirect_uri": settings.redirect_uri,
    }


async def complete_tiktok_ads_oauth(
    *, state: str, code: str | None, error: str | None, error_description: str | None
) -> dict[str, Any]:
    parsed = parse_signed_state(state)
    if parsed.get("flow") != "advertiser":
        raise TikTokOAuthStateError("Advertiser OAuth state is required")
    tenant_id = parsed["tenant_id"]
    actor = parsed["actor_user_id"]
    surface = parsed["return_surface"]
    try:
        with whatsapp_session() as session:
            repo = TikTokRepository(session)
            attempt = repo.consume_attempt(state_hash=parsed["state_hash"], signed_tenant_id=tenant_id)
            if attempt.tenant_id != tenant_id:
                raise TikTokOAuthStateError("OAuth state tenant mismatch")
            session.commit()
    except WhatsAppDatabaseUnavailable as exc:
        raise TikTokBusinessError(str(exc), code="TIKTOK_DB_UNAVAILABLE", http_status=503) from exc

    failed = oauth_completion_redirect_url(
        return_surface=surface, meta_connection="failed", extra_query={"tiktok_enhanced": "failed"}
    )
    if error:
        _persist_oauth_failure(tenant_id, actor, str(error_description or error))
        return {"redirect_url": failed}
    auth_code = str(code or "").strip()
    if not auth_code:
        raise TikTokOAuthStateError("TikTok advertiser authorization code is missing")

    try:
        token_payload = await exchange_ads_auth_code(auth_code=auth_code)
    except TikTokApiError as exc:
        _persist_oauth_failure(tenant_id, actor, exc.message, reason="waiting_for_permission")
        return {"redirect_url": failed}

    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    if not access_token:
        _persist_oauth_failure(tenant_id, actor, "missing_access_token", reason="waiting_for_permission")
        return {"redirect_url": failed}
    scopes = list(parse_scope_string(str(token_payload.get("scope") or "")))
    if isinstance(token_payload.get("scope"), list):
        scopes = [str(item) for item in token_payload["scope"] if str(item).strip()]

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        enhanced = TikTokEnhancedRepository(session)
        connection = repo.get_active_for_tenant(tenant_id)
        if connection is None:
            raise TikTokOAuthStateError("TikTok account connection is required")
        account_cred = connection.credential_id
        enhanced.store_advertiser_credential(
            connection=connection,
            access_token=access_token,
            refresh_token=refresh_token,
            scopes=scopes,
            access_expires_at=_expires(token_payload.get("expires_in")),
            refresh_expires_at=_expires(token_payload.get("refresh_token_expires_in")),
        )
        if connection.credential_id != account_cred:
            raise TikTokOAuthStateError("account-holder credential must not change during enhanced OAuth")
        repo.audit(
            tenant_id=tenant_id,
            connection_id=connection.id,
            actor=actor,
            event="enhanced_oauth_connected",
        )
        session.commit()
        connection_id = connection.id
        username = connection.username
        display_name = connection.display_name
        granted = list(connection.granted_scopes or [])

    with whatsapp_session() as session:
        enhanced = TikTokEnhancedRepository(session)
        await probe_enhanced_capabilities(
            repo=enhanced,
            tenant_id=tenant_id,
            connection_id=connection_id,
            username=username,
            display_name=display_name,
            granted_scopes=granted,
            force=True,
        )
        session.commit()

    return {
        "redirect_url": oauth_completion_redirect_url(
            return_surface=surface,
            meta_connection="success",
            extra_query={"tiktok_enhanced": "success"},
        ),
        "connection_id": connection_id,
    }


def _persist_oauth_failure(tenant_id: str, actor: str, detail: str, *, reason: str = "waiting_for_permission") -> None:
    try:
        with whatsapp_session() as session:
            repo = TikTokRepository(session)
            enhanced = TikTokEnhancedRepository(session)
            connection = repo.get_active_for_tenant(tenant_id)
            if connection is None:
                return
            binding = enhanced.get_or_create_binding(tenant_id=tenant_id, connection_id=connection.id)
            from services.tiktok_business.capabilities import empty_capabilities

            status = "waiting_for_permission" if reason == "waiting_for_permission" else "error"
            enhanced.apply_probe(
                binding,
                status=status,
                reason_code=reason,
                capabilities=empty_capabilities(),
            )
            repo.audit(
                tenant_id=tenant_id,
                connection_id=connection.id,
                actor=actor,
                event="enhanced_oauth_failed",
                detail=detail[:255],
            )
            session.commit()
    except Exception:
        return


async def ensure_fresh_advertiser_token(repo: TikTokEnhancedRepository, connection: Any) -> str | None:
    opened = repo.open_advertiser_tokens(tenant_id=connection.tenant_id, connection_id=connection.id)
    if opened is None:
        return None
    cred = opened.get("credential")
    access = str(opened.get("access_token") or "")
    refresh = str(opened.get("refresh_token") or "")
    if cred is None:
        return access or None
    skew = datetime.now(UTC) + timedelta(seconds=TOKEN_REFRESH_SKEW_SECONDS)
    if _aware(cred.access_expires_at) > skew:
        return access
    if not refresh:
        binding = repo.get_binding(tenant_id=connection.tenant_id, connection_id=connection.id)
        if binding is not None:
            binding.status = "reauthorization_required"
            binding.reason_code = "reauthorization_required"
        return None
    try:
        payload = await refresh_ads_access_token(refresh_token=refresh)
    except TikTokApiError:
        binding = repo.get_binding(tenant_id=connection.tenant_id, connection_id=connection.id)
        if binding is not None:
            binding.status = "reauthorization_required"
            binding.reason_code = "reauthorization_required"
        return None
    new_access = str(payload.get("access_token") or "").strip()
    new_refresh = str(payload.get("refresh_token") or refresh).strip()
    if not new_access:
        return None
    raw_scope = payload.get("scope")
    if isinstance(raw_scope, list):
        scopes = [str(item) for item in raw_scope if str(item).strip()]
    else:
        scopes = list(parse_scope_string(str(raw_scope or ""))) or list(opened.get("scopes") or [])
    repo.replace_advertiser_tokens(
        connection=connection,
        access_token=new_access,
        refresh_token=new_refresh,
        scopes=scopes,
        access_expires_at=_expires(payload.get("expires_in")),
        refresh_expires_at=_expires(payload.get("refresh_token_expires_in")),
    )
    if connection.credential_id == getattr(opened.get("credential"), "id", None):
        raise TikTokOAuthStateError("account-holder credential must stay separate")
    return new_access


async def disconnect_tiktok_enhanced(*, tenant_id: str, actor_user_id: str) -> None:
    token = ""
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        enhanced = TikTokEnhancedRepository(session)
        connection = repo.get_active_for_tenant(tenant_id)
        if connection is None:
            return
        token = enhanced.clear_enhanced(tenant_id=tenant_id, connection_id=connection.id)
        repo.audit(
            tenant_id=tenant_id,
            connection_id=connection.id,
            actor=actor_user_id,
            event="enhanced_disconnected",
        )
        session.commit()
    if token:
        try:
            await revoke_ads_access_token(access_token=token)
        except TikTokApiError:
            pass
