"""
Auth API Module
Handles authentication and user management endpoints for the dashboard.
Sessions are server-issued HttpOnly cookies; permissions enforced server-side.
"""

import asyncio
import os
import time
from typing import Any, Dict, Optional

from fastapi import Request, Response
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


def _cookie_samesite() -> str:
    value = (os.getenv("DASHBOARD_COOKIE_SAMESITE") or "lax").strip().lower()
    if value in {"lax", "strict", "none"}:
        return value.capitalize() if value != "none" else "none"
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


class CreateUserRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    role: Optional[str] = "viewer"
    permissions: Optional[Dict[str, bool]] = None
    status: Optional[str] = "active"


class UpdateUserRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    status: Optional[str] = None
    password: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class BootstrapAdminRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = "Admin"
    bootstrap_token: str


@app.on_event("startup")
async def ensure_default_admin():
    """
    Explicit bootstrap only. Never creates known default credentials.
    Enabled solely via AUTH_BOOTSTRAP_ADMIN_ON_STARTUP + AUTH_BOOTSTRAP_TOKEN
    and never in production.
    """
    if is_production_env():
        print("[auth_api] startup: production — skipping auto admin bootstrap")
        return
    toggle = os.getenv("AUTH_BOOTSTRAP_ADMIN_ON_STARTUP", "").strip().lower()
    if toggle not in {"1", "true", "yes", "on"}:
        print("[auth_api] startup: admin bootstrap disabled (set AUTH_BOOTSTRAP_ADMIN_ON_STARTUP to enable in non-prod)")
        return
    token = (os.getenv("AUTH_BOOTSTRAP_TOKEN") or "").strip()
    email = (os.getenv("AUTH_BOOTSTRAP_EMAIL") or "").strip().lower()
    password = os.getenv("AUTH_BOOTSTRAP_PASSWORD") or ""
    if not token or not email or not password:
        print("[auth_api] startup: bootstrap requested but AUTH_BOOTSTRAP_TOKEN/EMAIL/PASSWORD incomplete — skipped")
        return
    if len(password) < 12:
        print("[auth_api] startup: bootstrap password too short — skipped")
        return
    try:
        await asyncio.wait_for(
            asyncio.to_thread(_bootstrap_admin_if_empty, email, password, token),
            timeout=6.0,
        )
    except asyncio.TimeoutError:
        print("Warning: bootstrap admin timed out after 6s; startup will continue.")
    except Exception as e:
        print(f"Warning: Could not bootstrap admin: {e}")


def _bootstrap_admin_if_empty(email: str, password: str, token: str) -> None:
    expected = (os.getenv("AUTH_BOOTSTRAP_TOKEN") or "").strip()
    if not expected or token != expected:
        raise ValueError("Invalid bootstrap token")
    docs = list(
        user_service.collection.limit(1).stream(
            timeout=user_service.AUTH_QUERY_TIMEOUT_SECONDS,
            retry=None,
        )
    )
    if docs:
        print("[auth_api] bootstrap: users already exist — not creating admin")
        return
    user_service.create_user(
        {
            "email": email,
            "password": password,
            "name": os.getenv("AUTH_BOOTSTRAP_NAME") or "Admin",
            "role": "admin",
            "permissions": None,
            "status": "active",
        },
        created_by="bootstrap",
    )
    print(f"[auth_api] bootstrap: created initial admin for {email}")


@app.post("/api/auth/login")
async def login(request: LoginRequest, response: Response):
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
        except asyncio.TimeoutError:
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


@app.post("/api/auth/logout")
async def logout(request: Request, response: Response):
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    session_service.revoke_session(cookie)
    _clear_auth_cookies(response)
    return {"success": True}


@app.get("/api/auth/session")
async def validate_own_session(request: Request):
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
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": f"Session validation timeout ({AUTH_SESSION_TIMEOUT_SECONDS}s). Please retry.",
        }
    except Exception as e:
        print(f"[auth_api] session: Session validation error: {e}", flush=True)
        return {"success": False, "error": "Session validation failed"}


@app.get("/api/auth/session/{user_id}")
async def validate_session_legacy(user_id: str, request: Request):
    """
    Legacy path retained for compatibility but enforced against the cookie session.
    Callers may only request their own user_id.
    """
    session = require_session(request)
    if str(user_id) != str(session.user_id):
        return {"success": False, "error": "Forbidden"}
    return await validate_own_session(request)


@app.post("/api/auth/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response):
    session = require_session(request)
    try:
        success = user_service.change_password(
            session.user_id,
            body.current_password,
            body.new_password,
        )
        if not success:
            return {"success": False, "error": "Failed to change password"}
        # Invalidate all sessions for this user, then issue a fresh one
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


@app.post("/api/auth/bootstrap-admin")
async def bootstrap_admin(body: BootstrapAdminRequest):
    """
    One-time empty-database admin provision. Disabled in production unless
    AUTH_ALLOW_BOOTSTRAP_IN_PRODUCTION=true AND token matches (still requires empty users).
    """
    if is_production_env() and os.getenv("AUTH_ALLOW_BOOTSTRAP_IN_PRODUCTION", "").lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return {"success": False, "error": "Bootstrap disabled in production"}
    expected = (os.getenv("AUTH_BOOTSTRAP_TOKEN") or "").strip()
    if not expected or body.bootstrap_token != expected:
        return {"success": False, "error": "Invalid bootstrap token"}
    if len(body.password or "") < 12:
        return {"success": False, "error": "Password must be at least 12 characters"}
    try:
        await asyncio.to_thread(
            _bootstrap_admin_if_empty,
            (body.email or "").strip().lower(),
            body.password,
            body.bootstrap_token,
        )
        return {"success": True, "message": "Bootstrap completed or users already exist"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/auth/users")
async def get_users(request: Request):
    require_session(request)
    try:
        users = user_service.get_all_users()
        return {"success": True, "users": users}
    except Exception as e:
        print(f"Get users error: {e}")
        return {"success": False, "error": "Failed to fetch users"}


@app.post("/api/auth/users")
async def create_user(body: CreateUserRequest, request: Request):
    session = require_session(request)
    try:
        user = user_service.create_user(
            {
                "email": body.email,
                "password": body.password,
                "name": body.name,
                "role": body.role,
                "permissions": body.permissions,
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
async def update_user(user_id: str, body: UpdateUserRequest, request: Request):
    require_session(request)
    try:
        updates: Dict[str, Any] = {}
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
async def delete_user(user_id: str, request: Request):
    require_session(request)
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
