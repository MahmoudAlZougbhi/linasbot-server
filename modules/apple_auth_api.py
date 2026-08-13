"""Sign in with Apple mobile auth endpoints."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from modules.mobile_auth_api import issue_mobile_tokens
from services.apple_identity_service import (
    AppleIdentityError,
    find_active_apple_sub_for_user,
    find_by_apple_sub,
    get_or_create_app_account_token,
    link_apple_identity,
    unlink_all_apple_for_user,
    unlink_apple_identity,
)
from services.apple_revoke_outbox import maybe_store_refresh_from_authorization_code, revoke_on_account_delete
from services.apple_sign_in_service import AppleSignInError, is_private_relay_email, verify_identity_token
from services.dashboard_session_service import session_service
from services.mobile_refresh_token_service import mobile_refresh_token_service
from services.tenant_registration_service import allocate_tenant_id
from services.user_service import user_service

logger = logging.getLogger(__name__)


class AppleSignInRequest(BaseModel):
    identity_token: str = Field(min_length=16)
    nonce: str | None = None
    full_name: str | None = None
    email: str | None = None
    authorization_code: str | None = None


class AppleLinkRequest(BaseModel):
    identity_token: str = Field(min_length=16)
    nonce: str | None = None
    authorization_code: str | None = None


class AppleUnlinkRequest(BaseModel):
    identity_token: str | None = None
    sub: str | None = None
    nonce: str | None = None


def _email_hint(email: str) -> str:
    e = (email or "").strip().lower()
    if "@" not in e:
        return "***"
    local, _, domain = e.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def _compose_full_name(full_name: str | None) -> str | None:
    name = (full_name or "").strip()
    return name[:80] if name else None


def _resolve_email(*, claims: dict[str, Any], client_email: str | None) -> str | None:
    """Apple-attested email only. Client hint is accepted only when it matches token email."""
    token_email = (claims.get("email") or "").strip().lower() or None
    hint = (client_email or "").strip().lower() or None
    if token_email:
        if hint and hint != token_email:
            raise HTTPException(status_code=400, detail="email_hint_mismatch")
        return token_email
    # Never provision from client-supplied email alone (email squatting).
    return None


def _create_apple_account(*, email: str, display_name: str | None) -> dict[str, Any]:
    """Create tenant admin for first-time Apple sign-in (email may be private relay)."""
    business = (display_name or "").strip() or "Apple Account"
    tenant_id = allocate_tenant_id(business)
    random_password = secrets.token_urlsafe(48)
    # Do not invent a person's name — only persist client-provided display_name.
    name_for_user = display_name or email.split("@")[0]
    user = user_service.create_user(
        {
            "email": email,
            "password": random_password,
            "name": name_for_user,
            "displayName": display_name or name_for_user,
            "role": "admin",
            "permissions": None,
            "status": "active",
            "tenantId": tenant_id,
            "businessName": business[:120],
            "emailVerified": True,
            "passwordLoginEnabled": False,
        },
        created_by="apple-sign-in",
    )
    return user


def _issue_with_app_account_token(user: dict[str, Any]) -> dict[str, Any]:
    payload = issue_mobile_tokens(user)
    try:
        token = get_or_create_app_account_token(
            str(user.get("tenantId") or ""),
            str(user.get("id") or ""),
        )
        payload["app_account_token"] = token
    except Exception as exc:
        logger.info("apple app_account_token skipped: %s", type(exc).__name__)
    return payload


@app.post("/api/auth/mobile/apple")
async def mobile_apple_sign_in(body: AppleSignInRequest) -> Any:
    try:
        claims = verify_identity_token(body.identity_token, nonce=body.nonce)
    except AppleSignInError as exc:
        # Safe ops signal only — never log identity_token / authorization_code.
        logger.info("apple_sign_in_reject reason=%s", str(exc))
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    sub = str(claims["sub"])
    display_name = _compose_full_name(body.full_name)
    email = _resolve_email(claims=claims, client_email=body.email)
    relay = bool(claims.get("is_private_email")) or is_private_relay_email(email)

    identity = find_by_apple_sub(sub)
    if identity is not None:
        user = user_service.get_user_by_id(str(identity["user_id"]))
        if user is None or str(user.get("status") or "") != "active":
            raise HTTPException(status_code=401, detail="User not available")
        # Refresh display name on identity only when client sends one (first login).
        if display_name or email:
            try:
                link_apple_identity(
                    tenant_id=str(user.get("tenantId") or identity.get("tenant_id") or ""),
                    user_id=str(user["id"]),
                    sub=sub,
                    email=email or identity.get("email"),
                    is_private_relay=relay,
                    display_name=display_name,
                )
            except AppleIdentityError:
                pass
        maybe_store_refresh_from_authorization_code(
            user_id=str(user["id"]),
            sub=sub,
            authorization_code=body.authorization_code,
        )
        return _issue_with_app_account_token(user)

    if not email:
        raise HTTPException(
            status_code=400,
            detail="Email required for first Apple sign-in",
        )

    existing = user_service.get_user_by_email(email)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "link_required",
                "email_hint": _email_hint(email),
                "message": "An account with this email already exists. Sign in and link Apple.",
            },
        )

    try:
        user = _create_apple_account(email=email, display_name=display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        link_apple_identity(
            tenant_id=str(user.get("tenantId") or ""),
            user_id=str(user["id"]),
            sub=sub,
            email=email,
            is_private_relay=relay,
            display_name=display_name,
        )
    except AppleIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    maybe_store_refresh_from_authorization_code(
        user_id=str(user["id"]),
        sub=sub,
        authorization_code=body.authorization_code,
    )
    return _issue_with_app_account_token(user)


@app.post("/api/auth/mobile/apple/link")
async def mobile_apple_link(request: Request, body: AppleLinkRequest) -> Any:
    session = require_session(request)
    try:
        claims = verify_identity_token(body.identity_token, nonce=body.nonce)
    except AppleSignInError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    email = (claims.get("email") or "").strip().lower() or None
    relay = bool(claims.get("is_private_email")) or is_private_relay_email(email)
    sub = str(claims["sub"])
    try:
        identity = link_apple_identity(
            tenant_id=str(session.tenant_id),
            user_id=str(session.user_id),
            sub=sub,
            email=email,
            is_private_relay=relay,
            display_name=None,
        )
    except AppleIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    maybe_store_refresh_from_authorization_code(
        user_id=str(session.user_id),
        sub=sub,
        authorization_code=body.authorization_code,
    )
    token = get_or_create_app_account_token(str(session.tenant_id), str(session.user_id))
    return {
        "success": True,
        "linked": True,
        "provider": "apple",
        "app_account_token": token,
        "identity_id": identity.get("id"),
    }


@app.post("/api/auth/mobile/apple/unlink")
async def mobile_apple_unlink(request: Request, body: AppleUnlinkRequest | None = None) -> Any:
    session = require_session(request)
    payload = body or AppleUnlinkRequest()
    sub = (payload.sub or "").strip()
    if payload.identity_token:
        try:
            claims = verify_identity_token(payload.identity_token, nonce=payload.nonce)
        except AppleSignInError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        sub = str(claims["sub"])
    if not sub:
        sub = find_active_apple_sub_for_user(str(session.user_id)) or ""
    if not sub:
        raise HTTPException(status_code=400, detail="sub or identity_token required")

    try:
        unlink_apple_identity(user_id=str(session.user_id), sub=sub)
    except AppleIdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "unlinked": True}


@app.post("/api/auth/mobile/account/delete")
@app.delete("/api/auth/mobile/account")
async def mobile_account_delete(request: Request) -> Any:
    """Self-service account deletion (Apple Guideline 5.1.1). Preserves apple_transactions."""
    session = require_session(request)
    user_id = str(session.user_id)
    authorization_code: str | None = None
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            authorization_code = (str(raw.get("authorization_code") or "")).strip() or None
    except Exception:
        authorization_code = None
    # Revoke Apple tokens before soft-delete; durable outbox if HTTP fails.
    revoke_on_account_delete(user_id=user_id, authorization_code=authorization_code)
    unlink_all_apple_for_user(user_id)
    mobile_refresh_token_service.revoke_all_for_user(user_id)
    session_service.revoke_all_for_user(user_id)
    try:
        user_service.mark_self_service_deleted(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"success": True, "deleted": True}
