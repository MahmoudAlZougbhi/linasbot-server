"""
Auth API Module
Handles authentication and user management endpoints for the dashboard.
Sessions are server-issued HttpOnly cookies; permissions enforced server-side.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any, Literal, cast

from fastapi import HTTPException, Request, Response
from pydantic import BaseModel

from modules.api_security import is_production_env, require_session
from modules.core import app
from services.dashboard_session_service import (
    CSRF_COOKIE_NAME,
    SESSION_COOKIE_NAME,
    session_service,
)
from services.user_service import AuthBackendUnavailableError, user_service

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


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str | None = None


@app.on_event("startup")
async def ensure_auth_secret_configured() -> None:
    """
    Fail closed when production/test cannot sign sessions.
    First-admin provisioning is offline-only: scripts/provision_dashboard_admin.py
    (no public HTTP bootstrap, no startup password injection).
    """
    from services.dashboard_session_service import require_auth_secret_configured

    try:
        require_auth_secret_configured()
    except RuntimeError as exc:
        print(f"[auth_api] FATAL: {exc}", flush=True)
        raise
    print(
        "[auth_api] startup: auth secret OK — first admin via scripts/provision_dashboard_admin.py only",
        flush=True,
    )


@app.post("/api/auth/login")
async def login(request: LoginRequest, response: Response) -> Any:
    email = (request.email or "").strip().lower()
    password = request.password or ""

    max_retries = 3
    last_error_type = None

    for attempt in range(max_retries):
        try:
            user = await asyncio.wait_for(
                asyncio.to_thread(user_service.authenticate, email, password),
                timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
            )
            if not user:
                return {"success": False, "error": "Invalid email or password"}

            record = session_service.create_session(
                user_id=str(user["id"]),
                email=str(user.get("email") or email),
                role=str(user.get("role") or "viewer"),
                permissions=user.get("permissions"),
                tenant_id=str(user.get("tenantId") or "linas"),
                password_epoch=int(user.get("passwordEpoch") or user.get("password_epoch") or 0),
            )
            _set_auth_cookies(response, session_service.cookie_value_for(record), record.csrf_token)
            return {
                "success": True,
                "user": user,
                "csrf_token": record.csrf_token,
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except AuthBackendUnavailableError:
            last_error_type = "backend_unavailable"
            if attempt < max_retries - 1:
                await asyncio.sleep((attempt + 1) * 2)
            else:
                break
        except TimeoutError:
            last_error_type = "timeout"
            if attempt < max_retries - 1:
                await asyncio.sleep((attempt + 1) * 2)
            else:
                break
        except Exception as e:
            print(f"[auth_api] login: Login error: {e}", flush=True)
            return {"success": False, "error": "Login failed"}

    if last_error_type == "timeout":
        return {
            "success": False,
            "error": f"Authentication timeout ({AUTH_LOGIN_TIMEOUT_SECONDS}s). Please retry.",
        }
    return {
        "success": False,
        "error": "Authentication service temporarily unavailable (Firestore quota/network). Please retry in a few minutes.",
    }


@app.post("/api/auth/register")
async def register(request: RegisterRequest, response: Response) -> Any:
    """
    Public SaaS registration: create an isolated tenant admin and sign them in.
    Never creates users under the reserved ``linas`` tenant.
    """
    from services.tenant_registration_service import register_company_account

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                register_company_account,
                business_name=request.business_name,
                email=request.email,
                password=request.password,
                name=request.name,
            ),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except AuthBackendUnavailableError:
        return {
            "success": False,
            "error": "Authentication service temporarily unavailable. Please retry in a few minutes.",
        }
    except TimeoutError:
        return {
            "success": False,
            "error": f"Registration timeout ({AUTH_LOGIN_TIMEOUT_SECONDS}s). Please retry.",
        }
    except Exception as e:
        print(f"[auth_api] register: error: {e}", flush=True)
        return {"success": False, "error": "Registration failed"}

    user = result.user
    # Issue email verification token + attempt delivery (SMTP env required in production).
    try:
        from services.auth_email_tokens import auth_email_token_service
        from services.mail_service import public_app_base_url, send_email

        raw_verify = auth_email_token_service.issue(
            purpose="email_verify",
            user_id=str(user["id"]),
            email=str(user.get("email") or request.email),
            tenant_id=str(result.tenant_id),
        )
        verify_url = f"{public_app_base_url()}/verify-email?token={raw_verify}"
        send_email(
            to_email=str(user.get("email") or request.email),
            subject="Verify your Linas AI email",
            text_body=f"Verify your Linas AI email:\n\n{verify_url}\n",
            html_body=f'<p>Verify your Linas AI email:</p><p><a href="{verify_url}">Verify email</a></p>',
        )
    except Exception as exc:
        print(f"[auth_api] register: verify email dispatch failed: {exc}", flush=True)

    record = session_service.create_session(
        user_id=str(user["id"]),
        email=str(user.get("email") or request.email),
        role=str(user.get("role") or "admin"),
        permissions=user.get("permissions"),
        tenant_id=str(result.tenant_id),
        password_epoch=int(user.get("passwordEpoch") or user.get("password_epoch") or 0),
    )
    _set_auth_cookies(response, session_service.cookie_value_for(record), record.csrf_token)
    return {
        "success": True,
        "user": user,
        "tenant_id": result.tenant_id,
        "business_name": result.business_name,
        "csrf_token": record.csrf_token,
        "email_verification_required": not bool(user.get("emailVerified")),
    }


@app.post("/api/auth/forgot-password")
async def forgot_password(body: ForgotPasswordRequest) -> Any:
    """
    Always return a generic success message (do not reveal whether email exists).
    When SMTP is configured, send a time-limited reset link.
    """
    from services.auth_email_tokens import auth_email_token_service
    from services.mail_service import mail_configured, public_app_base_url, send_email

    email = (body.email or "").strip().lower()
    generic = {
        "success": True,
        "message": "If an account exists for that email, a password reset link has been sent.",
        "mail_configured": mail_configured(),
    }
    if not email or "@" not in email:
        return generic

    try:
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.get_user_by_email, email),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except Exception:
        return generic

    if not user or user.get("status") != "active":
        return generic

    raw_token = auth_email_token_service.issue(
        purpose="password_reset",
        user_id=str(user["id"]),
        email=str(user.get("email") or email),
        tenant_id=str(user.get("tenantId") or "linas"),
    )
    reset_url = f"{public_app_base_url()}/reset-password?token={raw_token}"
    text = (
        "Reset your Linas AI password using this link (expires in 1 hour):\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, you can ignore this email."
    )
    html = (
        "<p>Reset your Linas AI password using this link (expires in 1 hour):</p>"
        f'<p><a href="{reset_url}">Reset password</a></p>'
        "<p>If you did not request this, you can ignore this email.</p>"
    )
    result = send_email(to_email=email, subject="Reset your Linas AI password", text_body=text, html_body=html)
    payload = dict(generic)
    payload["mail_sent"] = bool(result.sent)
    if not result.sent and result.reason.startswith("smtp_not_configured"):
        payload["message"] = (
            "If an account exists for that email, a password reset was prepared. "
            "Mail delivery requires SMTP configuration on the server."
        )
    return payload


@app.post("/api/auth/reset-password")
async def reset_password(body: ResetPasswordRequest, response: Response) -> Any:
    from services.admin_provisioning_service import validate_provision_password
    from services.auth_email_tokens import auth_email_token_service

    token = (body.token or "").strip()
    if not token:
        return {"success": False, "error": "Reset token is required"}
    try:
        validate_provision_password(body.new_password or "")
    except ValueError as e:
        return {"success": False, "error": str(e)}

    record = auth_email_token_service.consume(token, "password_reset")
    if record is None:
        return {"success": False, "error": "Invalid or expired reset link"}

    try:
        await asyncio.wait_for(
            asyncio.to_thread(user_service.set_password_with_reset, record.user_id, body.new_password),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"[auth_api] reset-password error: {e}", flush=True)
        return {"success": False, "error": "Failed to reset password"}

    session_service.revoke_all_for_user(record.user_id)
    _clear_auth_cookies(response)
    return {"success": True, "message": "Password updated. You can sign in with your new password."}


@app.post("/api/auth/verify-email")
async def verify_email(body: VerifyEmailRequest) -> Any:
    from services.auth_email_tokens import auth_email_token_service

    token = (body.token or "").strip()
    if not token:
        return {"success": False, "error": "Verification token is required"}
    record = auth_email_token_service.consume(token, "email_verify")
    if record is None:
        return {"success": False, "error": "Invalid or expired verification link"}
    try:
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.mark_email_verified, record.user_id),
            timeout=AUTH_LOGIN_TIMEOUT_SECONDS,
        )
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"[auth_api] verify-email error: {e}", flush=True)
        return {"success": False, "error": "Failed to verify email"}
    return {"success": True, "message": "Email verified", "user": user}


@app.post("/api/auth/resend-verification")
async def resend_verification(body: ResendVerificationRequest, request: Request) -> Any:
    from services.auth_email_tokens import auth_email_token_service
    from services.mail_service import mail_configured, public_app_base_url, send_email

    email = (body.email or "").strip().lower()
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    session = session_service.get_valid_session(cookie)

    user = None
    if session is not None:
        user = user_service.get_user_by_id(session.user_id)
    elif email:
        user = user_service.get_user_by_email(email)

    generic = {
        "success": True,
        "message": "If verification is required, a new email has been sent.",
        "mail_configured": mail_configured(),
    }
    if not user or user.get("status") != "active":
        return generic
    if user_service.is_email_verified(user):
        return {"success": True, "message": "Email is already verified", "mail_configured": mail_configured()}

    auth_email_token_service.revoke_unused_for_user(str(user["id"]), "email_verify")
    raw_token = auth_email_token_service.issue(
        purpose="email_verify",
        user_id=str(user["id"]),
        email=str(user.get("email") or ""),
        tenant_id=str(user.get("tenantId") or "linas"),
    )
    verify_url = f"{public_app_base_url()}/verify-email?token={raw_token}"
    text = f"Verify your Linas AI email address:\n\n{verify_url}\n\nThis link expires in 48 hours."
    html = (
        "<p>Verify your Linas AI email address:</p>"
        f'<p><a href="{verify_url}">Verify email</a></p>'
        "<p>This link expires in 48 hours.</p>"
    )
    result = send_email(
        to_email=str(user.get("email") or ""),
        subject="Verify your Linas AI email",
        text_body=text,
        html_body=html,
    )
    payload = dict(generic)
    payload["mail_sent"] = bool(result.sent)
    return payload


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response) -> Any:
    """
    Logout requires an authenticated session; CSRF is enforced by middleware.
    Revokes the caller's server-side session and clears cookies.
    """
    session = require_session(request)
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    # Revoke the cookie-bound session (must match the authenticated principal)
    record = session_service.get_valid_session(cookie)
    if record is None or str(record.user_id) != str(session.user_id):
        _clear_auth_cookies(response)
        return {"success": False, "error": "Session mismatch"}
    session_service.revoke_session(cookie)
    _clear_auth_cookies(response)
    return {"success": True}


@app.get("/api/auth/session")
async def validate_own_session(request: Request) -> Any:
    """Return the authenticated caller's user profile (no user_id in path — closes IDOR)."""
    session = require_session(request)
    try:
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.get_user_by_id, session.user_id),
            timeout=AUTH_SESSION_TIMEOUT_SECONDS,
        )
        if not user or user.get("status") != "active":
            return {"success": False, "error": "User not found or inactive"}
        sanitized = user_service._sanitize_user(user)
        return {
            "success": True,
            "user": sanitized,
            "csrf_token": session.csrf_token,
        }
    except TimeoutError:
        return {
            "success": False,
            "error": f"Session validation timeout ({AUTH_SESSION_TIMEOUT_SECONDS}s). Please retry.",
        }
    except Exception as e:
        print(f"[auth_api] session: Session validation error: {e}", flush=True)
        return {"success": False, "error": "Session validation failed"}


@app.get("/api/auth/session/{user_id}")
async def validate_session_legacy(user_id: str, request: Request) -> Any:
    """
    Legacy path retained for compatibility but enforced against the cookie session.
    Callers may only request their own user_id.
    """
    session = require_session(request)
    if str(user_id) != str(session.user_id):
        return {"success": False, "error": "Forbidden"}
    return await validate_own_session(request)


@app.post("/api/auth/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response) -> Any:
    session = require_session(request)
    try:
        success = user_service.change_password(
            session.user_id,
            body.current_password,
            body.new_password,
        )
        if not success:
            return {"success": False, "error": "Failed to change password"}
        # Invalidate all sessions for this user, then issue a fresh one at the new epoch
        session_service.revoke_all_for_user(session.user_id)
        user = user_service.get_user_by_id(session.user_id)
        if not user:
            _clear_auth_cookies(response)
            return {"success": True, "message": "Password changed successfully"}
        record = session_service.create_session(
            user_id=str(user["id"]),
            email=str(user.get("email") or session.email),
            role=str(user.get("role") or session.role),
            permissions=user.get("permissions"),
            tenant_id=str(user.get("tenantId") or session.tenant_id),
            password_epoch=int(user.get("passwordEpoch") or user.get("password_epoch") or 0),
        )
        _set_auth_cookies(response, session_service.cookie_value_for(record), record.csrf_token)
        return {
            "success": True,
            "message": "Password changed successfully",
            "csrf_token": record.csrf_token,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"Change password error: {e}")
        return {"success": False, "error": "Failed to change password"}


@app.get("/api/auth/users")
async def get_users(request: Request) -> Any:
    session = require_session(request)
    try:
        users = [
            user for user in user_service.get_all_users() if str(user.get("tenantId") or "linas") == session.tenant_id
        ]
        return {"success": True, "users": users}
    except Exception as e:
        print(f"Get users error: {e}")
        return {"success": False, "error": "Failed to fetch users"}


@app.post("/api/auth/users")
async def create_user(body: CreateUserRequest, request: Request) -> Any:
    session = require_session(request)
    requested_tenant = (body.tenant_id or session.tenant_id).strip()
    if requested_tenant != session.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant user provisioning is forbidden")
    try:
        user = user_service.create_user(
            {
                "email": body.email,
                "password": body.password,
                "name": body.name,
                "role": body.role,
                "permissions": body.permissions,
                "tenantId": session.tenant_id,
                "status": body.status,
            },
            created_by=session.user_id,
        )
        return {"success": True, "user": user, "message": "User created successfully"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"Create user error: {e}")
        return {"success": False, "error": "Failed to create user"}


@app.put("/api/auth/users/{user_id}")
async def update_user(user_id: str, body: UpdateUserRequest, request: Request) -> Any:
    session = require_session(request)
    target = user_service.get_user_by_id(user_id)
    if target is None or str(target.get("tenantId") or "linas") != session.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    if body.tenant_id is not None and body.tenant_id.strip() != session.tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant user reassignment is forbidden")
    try:
        updates: dict[str, Any] = {}
        if body.name is not None:
            updates["name"] = body.name
        if body.role is not None:
            updates["role"] = body.role
        if body.permissions is not None:
            updates["permissions"] = body.permissions
        if body.status is not None:
            updates["status"] = body.status
        if body.password is not None:
            updates["password"] = body.password
        user = user_service.update_user(user_id, updates)
        if body.password is not None:
            session_service.revoke_all_for_user(user_id)
        return {"success": True, "user": user, "message": "User updated successfully"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"Update user error: {e}")
        return {"success": False, "error": "Failed to update user"}


@app.delete("/api/auth/users/{user_id}")
async def delete_user(user_id: str, request: Request) -> Any:
    session = require_session(request)
    target = user_service.get_user_by_id(user_id)
    if target is None or str(target.get("tenantId") or "linas") != session.tenant_id:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        success = user_service.delete_user(user_id)
        if success:
            session_service.revoke_all_for_user(user_id)
            return {"success": True, "message": "User deleted successfully"}
        return {"success": False, "error": "Failed to delete user"}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"Delete user error: {e}")
        return {"success": False, "error": "Failed to delete user"}
