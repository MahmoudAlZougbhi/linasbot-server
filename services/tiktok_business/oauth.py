"""Official TikTok Business OAuth start, callback, refresh, revoke."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
from services.meta_oauth_return import oauth_completion_redirect_url
from services.tiktok_business.config import (
    REQUESTED_SCOPES,
    TIKTOK_AUTHORIZE_URL,
    TOKEN_REFRESH_SKEW_SECONDS,
    parse_scope_string,
    require_tiktok_settings,
    tiktok_redirect_uri,
)
from services.tiktok_business.entitlement import assert_tiktok_plan_allowed
from services.tiktok_business.errors import TikTokApiError, TikTokBusinessError, TikTokOAuthStateError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.oauth_state import create_signed_state, parse_signed_state
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.scopes import comments_manage_ready, missing_requested, profile_ready


def _expires(seconds: Any) -> datetime:
    try:
        value = int(seconds or 0)
    except (TypeError, ValueError):
        value = 0
    return datetime.now(UTC) + timedelta(seconds=max(value, 0))


async def fetch_profile(*, access_token: str, open_id: str) -> dict[str, str]:
    data = await tiktok_request(
        method="GET",
        path="/business/get/",
        access_token=access_token,
        params={
            "business_id": open_id,
            "fields": '["display_name","username","profile_image"]',
        },
    )
    return {
        "display_name": str(data.get("display_name") or ""),
        "username": str(data.get("username") or ""),
        "avatar_url": str(data.get("profile_image") or data.get("profile_image_url") or ""),
    }


async def exchange_auth_code(*, auth_code: str) -> dict[str, Any]:
    settings = require_tiktok_settings()
    return await tiktok_request(
        method="POST",
        path="/tt_user/oauth2/token/",
        json_body={
            "client_id": settings.client_key,
            "client_secret": settings.client_secret,
            "grant_type": "authorization_code",
            "auth_code": auth_code,
            "redirect_uri": settings.redirect_uri,
        },
    )


async def refresh_access_token(*, refresh_token: str) -> dict[str, Any]:
    settings = require_tiktok_settings()
    return await tiktok_request(
        method="POST",
        path="/tt_user/oauth2/refresh_token/",
        json_body={
            "client_id": settings.client_key,
            "client_secret": settings.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )


async def revoke_access_token(*, access_token: str) -> None:
    settings = require_tiktok_settings()
    await tiktok_request(
        method="POST",
        path="/tt_user/oauth2/revoke/",
        json_body={
            "client_id": settings.client_key,
            "client_secret": settings.client_secret,
            "access_token": access_token,
        },
    )


def start_tiktok_oauth(*, tenant_id: str, actor_user_id: str, return_surface: str = "mobile") -> dict[str, Any]:
    require_tiktok_settings()
    assert_tiktok_plan_allowed(tenant_id)
    signed = create_signed_state(tenant_id=tenant_id, actor_user_id=actor_user_id, return_surface=return_surface)
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        surface = return_surface if return_surface in {"mobile", "web"} else "web"
        repo.create_attempt(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            return_surface=surface,
            state_hash=signed.state_hash,
            expires_at=datetime.fromtimestamp(signed.expires_at_unix, tz=UTC),
        )
        repo.audit(tenant_id=tenant_id, connection_id=None, actor=actor_user_id, event="oauth_start")
        session.commit()
    settings = require_tiktok_settings()
    query = urlencode(
        {
            "client_key": settings.client_key,
            "response_type": "code",
            "scope": ",".join(REQUESTED_SCOPES),
            "redirect_uri": settings.redirect_uri,
            "state": signed.state,
        }
    )
    return {
        "success": True,
        "authorization_url": f"{TIKTOK_AUTHORIZE_URL}?{query}",
        "redirect_uri": settings.redirect_uri,
    }


async def complete_tiktok_oauth(
    *, state: str, code: str | None, error: str | None, error_description: str | None
) -> dict[str, Any]:
    parsed = parse_signed_state(state)
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

    if error:
        return {
            "redirect_url": oauth_completion_redirect_url(
                return_surface=surface, meta_connection="failed", extra_query={"tiktok_connection": "failed"}
            )
        }
    auth_code = str(code or "").strip()
    if not auth_code:
        raise TikTokOAuthStateError("TikTok authorization code is missing")

    token_payload = await exchange_auth_code(auth_code=auth_code)
    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    open_id = str(token_payload.get("open_id") or "").strip()
    if not access_token or not open_id:
        raise TikTokApiError("TikTok token response missing access_token or open_id")
    scopes = list(parse_scope_string(str(token_payload.get("scope") or "")))
    profile = {"display_name": "", "username": "", "avatar_url": ""}
    if profile_ready(scopes):
        try:
            profile = await fetch_profile(access_token=access_token, open_id=open_id)
        except TikTokApiError:
            profile = {"display_name": "", "username": "", "avatar_url": ""}
    missing = missing_requested(scopes)
    lifecycle = "connected" if comments_manage_ready(scopes) or not missing else "permission_required"
    if missing and not comments_manage_ready(scopes) and "comment.list" not in scopes:
        lifecycle = "permission_required"

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.upsert_connection(
            tenant_id=tenant_id,
            actor_user_id=actor,
            open_id=open_id,
            display_name=profile["display_name"],
            username=profile["username"],
            avatar_url=profile["avatar_url"],
            scopes=scopes,
            access_token=access_token,
            refresh_token=refresh_token,
            access_expires_at=_expires(token_payload.get("expires_in")),
            refresh_expires_at=_expires(token_payload.get("refresh_token_expires_in")),
            lifecycle_status=lifecycle,
        )
        session.commit()
        connection_id = connection.id

    status = "success" if lifecycle in {"connected", "permission_required"} else "failed"
    try:
        from services.tiktok_business.toggles import enable_tiktok_comments_after_connect

        await enable_tiktok_comments_after_connect(tenant_id=tenant_id, actor=actor)
    except Exception:
        pass
    return {
        "redirect_url": oauth_completion_redirect_url(
            return_surface=surface,
            meta_connection=status,
            extra_query={"tiktok_connection": status},
        ),
        "connection_id": connection_id,
        "lifecycle_status": lifecycle,
    }


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def ensure_fresh_token(repo: TikTokRepository, connection: Any) -> str:
    opened = repo.open_tokens(connection)
    access = str(opened.get("access_token") or "")
    refresh = str(opened.get("refresh_token") or "")
    cred_id = connection.credential_id
    from db.models.tiktok_business import TikTokCredential

    cred = repo.session.get(TikTokCredential, cred_id) if cred_id else None
    if cred is None:
        raise TikTokOAuthStateError("TikTok credential is unavailable")
    skew = datetime.now(UTC) + timedelta(seconds=TOKEN_REFRESH_SKEW_SECONDS)
    if _aware(cred.access_expires_at) > skew:
        return access
    if not refresh:
        connection.lifecycle_status = "token_expired"
        raise TikTokOAuthStateError("TikTok refresh token is missing")
    payload = await refresh_access_token(refresh_token=refresh)
    new_access = str(payload.get("access_token") or "").strip()
    new_refresh = str(payload.get("refresh_token") or refresh).strip()
    scopes = list(parse_scope_string(str(payload.get("scope") or ""))) or list(connection.granted_scopes or [])
    if not new_access:
        connection.lifecycle_status = "token_expired"
        raise TikTokApiError("TikTok refresh did not return access_token")
    repo.replace_tokens(
        connection,
        access_token=new_access,
        refresh_token=new_refresh,
        scopes=scopes,
        access_expires_at=_expires(payload.get("expires_in")),
        refresh_expires_at=_expires(payload.get("refresh_token_expires_in")),
    )
    return new_access


async def disconnect_tiktok(*, tenant_id: str, actor_user_id: str) -> None:
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.get_active_for_tenant(tenant_id)
        if connection is None:
            return
        token = ""
        try:
            token = str(repo.open_tokens(connection).get("access_token") or "")
        except Exception:
            token = ""
        if token:
            try:
                await revoke_access_token(access_token=token)
            except TikTokApiError:
                pass
        repo.mark_revoked(connection, actor=actor_user_id, reason="user_disconnect")
        session.commit()


def production_redirect_uri() -> str:
    return tiktok_redirect_uri()
