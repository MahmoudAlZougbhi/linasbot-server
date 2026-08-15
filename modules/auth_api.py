"""
Auth API Module
Handles authentication and user management endpoints for the dashboard.
Sessions are server-issued HttpOnly cookies; permissions enforced server-side.

Shared models/cookies: auth_api_common; user CRUD: auth_users_api (LOC split).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request, Response

from modules.api_security import require_session
from modules.auth_api_common import (  # noqa: F401
    AUTH_LOGIN_TIMEOUT_SECONDS,
    AUTH_SESSION_TIMEOUT_SECONDS,
    ChangePasswordRequest,
    CreateUserRequest,
    LoginRequest,
    RegisterRequest,
    UpdateUserRequest,
    _clear_auth_cookies,
    _cookie_samesite,
    _cookie_secure,
    _set_auth_cookies,
)

# Register user CRUD + public email-token routes (LOC split).
from modules.auth_email_routes import (  # noqa: E402, F401
    forgot_password,
    resend_verification,
    reset_password,
    verify_email,
)
from modules.auth_users_api import (  # noqa: E402, F401
    create_user,
    delete_user,
    get_users,
    update_user,
)
from modules.core import app
from services.dashboard_session_service import (
    SESSION_COOKIE_NAME,
    session_service,
)
from services.user_service import AuthBackendUnavailableError, user_service


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


@app.on_event("startup")
async def ensure_model_policy_configured() -> None:
    """Fail closed when env tries to silently override Sol/Terra routing policy."""
    from services.model_policy import validate_model_policy_config

    try:
        snap = validate_model_policy_config()
    except RuntimeError as exc:
        print(f"[model_policy] FATAL: {exc}", flush=True)
        raise
    print(
        "[model_policy] startup OK — "
        f"owner={snap['owner_model']} customer={snap['customer_model']} "
        f"mode={snap['reasoning_mode']}",
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

            tenant_id = str(user.get("tenantId") or "").strip()
            if not tenant_id:
                return {"success": False, "error": "Tenant required"}

            record = session_service.create_session(
                user_id=str(user["id"]),
                email=str(user.get("email") or email),
                role=str(user.get("role") or "viewer"),
                permissions=user.get("permissions"),
                tenant_id=tenant_id,
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
                name=request.name or request.display_name,
                display_name=request.display_name or request.name,
                gender=request.gender,
                preferred_language=request.preferred_language,
                form_of_address=request.form_of_address,
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
    # Issue email verification token + attempt delivery (Resend/SMTP env required in production).
    try:
        from services.auth_email_tokens import auth_email_token_service
        from services.email_dispatch import send_verify_email

        issued = auth_email_token_service.issue(
            purpose="email_verify",
            user_id=str(user["id"]),
            email=str(user.get("email") or request.email),
            tenant_id=str(result.tenant_id),
        )
        send_verify_email(
            to_email=str(user.get("email") or request.email),
            raw_token=issued,
            otp_code=issued.otp,
            locale=str(user.get("preferredLanguage") or request.preferred_language or "en"),
            user_id=str(user["id"]),
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
            tenant_id=str(user.get("tenantId") or session.tenant_id or "").strip(),
            password_epoch=int(user.get("passwordEpoch") or user.get("password_epoch") or 0),
        )
        _set_auth_cookies(response, session_service.cookie_value_for(record), record.csrf_token)
        try:
            from modules.auth_email_change_api import notify_password_changed

            notify_password_changed(
                user_id=str(user["id"]),
                email=str(user.get("email") or session.email),
                locale=str(user.get("preferredLanguage") or "en"),
            )
        except Exception:
            pass
        return {"success": True, "message": "Password changed successfully", "csrf_token": record.csrf_token}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        print(f"Change password error: {e}")
        return {"success": False, "error": "Failed to change password"}
