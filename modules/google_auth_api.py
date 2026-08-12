"""Google Sign-In mobile auth endpoints (mirror Apple; prevent email duplicates)."""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from modules.api_security import require_session
from modules.core import app
from modules.mobile_auth_api import issue_mobile_tokens
from services.google_identity_service import (
    GoogleIdentityError,
    find_active_google_sub_for_user,
    find_by_google_sub,
    link_google_identity,
    unlink_google_identity,
)
from services.google_sign_in_service import GoogleSignInError, verify_identity_token
from services.tenant_registration_service import allocate_tenant_id
from services.user_service import user_service

logger = logging.getLogger(__name__)


class GoogleSignInRequest(BaseModel):
    identity_token: str = Field(min_length=16)
    nonce: str | None = None
    full_name: str | None = None
    email: str | None = None


class GoogleLinkRequest(BaseModel):
    identity_token: str = Field(min_length=16)
    nonce: str | None = None


class GoogleUnlinkRequest(BaseModel):
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


def _compose_full_name(full_name: str | None, claims_name: str | None) -> str | None:
    for candidate in (full_name, claims_name):
        name = (candidate or "").strip()
        if name:
            return name[:80]
    return None


def _resolve_email(*, claims: dict[str, Any], client_email: str | None) -> str | None:
    token_email = (claims.get("email") or "").strip().lower() or None
    hint = (client_email or "").strip().lower() or None
    if token_email:
        if hint and hint != token_email:
            raise HTTPException(status_code=400, detail="email_hint_mismatch")
        return token_email
    return None


def _create_google_account(*, email: str, display_name: str | None) -> dict[str, Any]:
    business = (display_name or "").strip() or "Google Account"
    tenant_id = allocate_tenant_id(business)
    random_password = secrets.token_urlsafe(48)
    name_for_user = display_name or email.split("@")[0]
    return user_service.create_user(
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
        created_by="google-sign-in",
    )


@app.post("/api/auth/mobile/google")
async def mobile_google_sign_in(body: GoogleSignInRequest) -> Any:
    try:
        claims = verify_identity_token(body.identity_token, nonce=body.nonce)
    except GoogleSignInError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    sub = str(claims["sub"])
    display_name = _compose_full_name(body.full_name, claims.get("name"))
    email = _resolve_email(claims=claims, client_email=body.email)

    identity = find_by_google_sub(sub)
    if identity is not None:
        user = user_service.get_user_by_id(str(identity["user_id"]))
        if user is None or str(user.get("status") or "") != "active":
            raise HTTPException(status_code=401, detail="User not available")
        if display_name or email:
            try:
                link_google_identity(
                    tenant_id=str(user.get("tenantId") or identity.get("tenant_id") or ""),
                    user_id=str(user["id"]),
                    sub=sub,
                    email=email or identity.get("email"),
                    display_name=display_name,
                )
            except GoogleIdentityError:
                pass
        return issue_mobile_tokens(user)

    if not email:
        raise HTTPException(status_code=400, detail="Email required for first Google sign-in")

    existing = user_service.get_user_by_email(email)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "link_required",
                "email_hint": _email_hint(email),
                "message": "An account with this email already exists. Sign in and link Google.",
            },
        )

    try:
        user = _create_google_account(email=email, display_name=display_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        link_google_identity(
            tenant_id=str(user.get("tenantId") or ""),
            user_id=str(user["id"]),
            sub=sub,
            email=email,
            display_name=display_name,
        )
    except GoogleIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return issue_mobile_tokens(user)


@app.post("/api/auth/mobile/google/link")
async def mobile_google_link(request: Request, body: GoogleLinkRequest) -> Any:
    session = require_session(request)
    try:
        claims = verify_identity_token(body.identity_token, nonce=body.nonce)
    except GoogleSignInError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    email = (claims.get("email") or "").strip().lower() or None
    sub = str(claims["sub"])
    try:
        identity = link_google_identity(
            tenant_id=str(session.tenant_id),
            user_id=str(session.user_id),
            sub=sub,
            email=email,
            display_name=None,
        )
    except GoogleIdentityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "success": True,
        "linked": True,
        "provider": "google",
        "identity_id": identity.get("id"),
    }


@app.post("/api/auth/mobile/google/unlink")
async def mobile_google_unlink(request: Request, body: GoogleUnlinkRequest | None = None) -> Any:
    session = require_session(request)
    payload = body or GoogleUnlinkRequest()
    sub = (payload.sub or "").strip()
    if payload.identity_token:
        try:
            claims = verify_identity_token(payload.identity_token, nonce=payload.nonce)
        except GoogleSignInError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        sub = str(claims["sub"])
    if not sub:
        sub = find_active_google_sub_for_user(str(session.user_id)) or ""
    if not sub:
        raise HTTPException(status_code=400, detail="sub or identity_token required")

    try:
        unlink_google_identity(user_id=str(session.user_id), sub=sub)
    except GoogleIdentityError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"success": True, "unlinked": True}
