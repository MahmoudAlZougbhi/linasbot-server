"""Shared auth API models, cookie helpers, and timeouts (LOC split from auth_api)."""

from __future__ import annotations

import os
from typing import Literal, cast

from fastapi import Response
from pydantic import BaseModel

from modules.api_security import is_production_env
from services.dashboard_session_service import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
)

AUTH_LOGIN_TIMEOUT_SECONDS = float(os.getenv("AUTH_LOGIN_TIMEOUT_SECONDS", "12"))
AUTH_SESSION_TIMEOUT_SECONDS = float(os.getenv("AUTH_SESSION_TIMEOUT_SECONDS", "8"))


def _cookie_secure() -> bool:
    if os.getenv("DASHBOARD_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if os.getenv("DASHBOARD_COOKIE_SECURE", "").strip().lower() in {"0", "false", "no", "off"}:
        return False
    return is_production_env()


def _cookie_samesite() -> Literal["lax", "strict", "none"]:
    value = (os.getenv("DASHBOARD_COOKIE_SAMESITE") or "lax").strip().lower()
    if value in {"lax", "strict", "none"}:
        return cast(Literal["lax", "strict", "none"], value)
    return "lax"


def _set_auth_cookies(response: Response, cookie_value: str, csrf_token: str) -> None:
    secure = _cookie_secure()
    samesite = _cookie_samesite()
    # SameSite=None requires Secure
    if samesite.lower() == "none":
        secure = True
    max_age = int(os.getenv("DASHBOARD_SESSION_TTL_SECONDS", str(12 * 60 * 60)))
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie_value,
        httponly=True,
        secure=secure,
        samesite=samesite,
        max_age=max_age,
        path="/",
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=secure,
        samesite=samesite,
        max_age=max_age,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    business_name: str
    email: str
    password: str
    name: str | None = None
    display_name: str | None = None
    gender: str | None = None  # male | female | unset — never inferred server-side
    preferred_language: str | None = None  # ar | en | fr
    form_of_address: str | None = None


class CreateUserRequest(BaseModel):
    email: str
    password: str
    name: str | None = None
    role: str | None = "viewer"
    permissions: dict[str, bool] | None = None
    tenant_id: str | None = None
    status: str | None = "active"


class UpdateUserRequest(BaseModel):
    name: str | None = None
    role: str | None = None
    permissions: dict[str, bool] | None = None
    tenant_id: str | None = None
    status: str | None = None
    password: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    email: str | None = None


class VerifyEmailRequest(BaseModel):
    token: str
    email: str | None = None


class ResendVerificationRequest(BaseModel):
    email: str | None = None
