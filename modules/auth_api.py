"""
Auth API Module
Handles authentication and user management endpoints for the dashboard
"""

import asyncio
import os
import time

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional, List

from modules.core import app
from services.user_service import user_service, AuthBackendUnavailableError


# Auth timeout (per attempt) - reduced from 45s to avoid long hangs
AUTH_LOGIN_TIMEOUT_SECONDS = float(os.getenv("AUTH_LOGIN_TIMEOUT_SECONDS", "12"))
AUTH_SESSION_TIMEOUT_SECONDS = float(os.getenv("AUTH_SESSION_TIMEOUT_SECONDS", "8"))

# Emergency local fallback (disabled by default).
# Enable only when Firestore is quota-limited and operators must access dashboard.
AUTH_FALLBACK_ENABLED = os.getenv(
    "ENABLE_AUTH_FALLBACK_WHEN_FIRESTORE_DOWN", "false"
).strip().lower() == "true"
AUTH_FALLBACK_EMAIL = os.getenv("AUTH_FALLBACK_EMAIL", "admin@lina.com").strip().lower()
AUTH_FALLBACK_PASSWORD = os.getenv("AUTH_FALLBACK_PASSWORD", "admin123")
AUTH_FALLBACK_USER_ID = os.getenv("AUTH_FALLBACK_USER_ID", "local-admin-fallback")


def _build_auth_fallback_user(email: str) -> Dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    return {
        "id": AUTH_FALLBACK_USER_ID,
        "email": email,
        "name": "Local Admin",
        "role": "admin",
        "permissions": None,
        "status": "active",
        "lastLogin": now,
        "createdAt": now,
        "createdBy": "system",
        "updatedAt": now,
    }


# ==========================================
# Request/Response Models
# ==========================================

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
    password: Optional[str] = None  # For admin password reset


class ChangePasswordRequest(BaseModel):
    user_id: str
    current_password: str
    new_password: str


# ==========================================
# Startup Event - Ensure Default Admin
# ==========================================

@app.on_event("startup")
async def ensure_default_admin():
    """Ensure default admin exists on startup"""
    toggle = os.getenv("AUTH_ENSURE_DEFAULT_ADMIN_ON_STARTUP")
    if toggle is None:
        env_name = (
            os.getenv("ENVIRONMENT")
            or os.getenv("ENV")
            or ""
        ).strip().lower()
        enabled = env_name not in {"prod", "production"}
    else:
        enabled = str(toggle).strip().lower() in {"1", "true", "yes", "on"}

    if not enabled:
        print("[auth_api] startup: skipping ensure_default_admin (disabled by config)")
        return

    try:
        # Firestore calls are synchronous; run them off the event loop and
        # fail open on timeout so API startup never hangs.
        await asyncio.wait_for(
            asyncio.to_thread(user_service.ensure_default_admin),
            timeout=6.0
        )
    except asyncio.TimeoutError:
        print("Warning: ensure_default_admin timed out after 6s; startup will continue.")
    except Exception as e:
        print(f"Warning: Could not ensure default admin: {e}")


# ==========================================
# Authentication Endpoints
# ==========================================

@app.post("/api/auth/login")
async def login(request: LoginRequest):
    """
    Authenticate user with email and password

    Returns user data (without password) on success
    """
    # Normalize email before auth
    email = (request.email or "").strip().lower()
    password = request.password or ""

    max_retries = 3
    last_error = None
    last_error_type = None  # "timeout" | "backend_unavailable"

    for attempt in range(max_retries):
        try:
            t0 = time.monotonic()
            print(f"[auth_api] login: REQUEST_RECEIVED for {email} attempt {attempt + 1}/{max_retries} t=0", flush=True)
            # Check Firestore state (diagnostic - first access may trigger lazy init)
            try:
                import utils.utils as u
                fs_ready = getattr(u, "_firestore_init_done", False)
            except Exception:
                fs_ready = False
            print(f"[auth_api] login: Firestore init_done={fs_ready}, calling authenticate (watch backend stdout for [auth:...] logs)", flush=True)
            print(f"[auth_api] login: authenticate START", flush=True)
            user = await asyncio.wait_for(
                asyncio.to_thread(user_service.authenticate, email, password),
                timeout=AUTH_LOGIN_TIMEOUT_SECONDS
            )
            elapsed = time.monotonic() - t0
            print(f"[auth_api] login: authenticate RETURNED in {elapsed:.3f}s", flush=True)

            if not user:
                return {
                    "success": False,
                    "error": "Invalid email or password"
                }

            print(f"[auth_api] login: returning success", flush=True)
            return {
                "success": True,
                "user": user
            }
        except ValueError as e:
            return {
                "success": False,
                "error": str(e)
            }
        except AuthBackendUnavailableError as e:
            last_error = e
            last_error_type = "backend_unavailable"
            if attempt < max_retries - 1:
                delay = (attempt + 1) * 2  # 2s, 4s
                print(f"[auth_api] login: BACKEND_UNAVAILABLE, retrying in {delay}s...", flush=True)
                await asyncio.sleep(delay)
            else:
                break
        except asyncio.TimeoutError:
            last_error_type = "timeout"
            print(f"[auth_api] login: TIMEOUT after {AUTH_LOGIN_TIMEOUT_SECONDS}s for {email} (attempt {attempt + 1}/{max_retries})", flush=True)
            print(f"[auth_api] login: DIAGNOSTIC - Check LAST [auth:...] log above to see where it hung: get_user_by_email query.stream() vs bcrypt", flush=True)
            if attempt < max_retries - 1:
                delay = (attempt + 1) * 2  # 2s, 4s
                print(f"[auth_api] login: retrying in {delay}s...", flush=True)
                await asyncio.sleep(delay)
            else:
                break
        except Exception as e:
            print(f"[auth_api] login: Login error: {e}", flush=True)
            return {
                "success": False,
                "error": "Login failed"
            }

    # All retries exhausted - return appropriate error
    if last_error_type == "timeout":
        return {
            "success": False,
            "error": f"Authentication timeout ({AUTH_LOGIN_TIMEOUT_SECONDS}s). تحقق من Firestore أو أعد تشغيل الـ backend."
        }

    # AuthBackendUnavailableError (Firestore quota/network)
    if last_error is not None:
        # Optional emergency path: allow dashboard login while Firestore is down.
        if (
            AUTH_FALLBACK_ENABLED
            and email == AUTH_FALLBACK_EMAIL
            and password == AUTH_FALLBACK_PASSWORD
        ):
            print(
                f"[auth_api] login: FALLBACK_LOGIN_GRANTED for {email} (Firestore unavailable)",
                flush=True,
            )
            return {
                "success": True,
                "user": _build_auth_fallback_user(email),
            }
        print(f"[auth_api] login: BACKEND_UNAVAILABLE for {email}: {last_error}", flush=True)
        return {
            "success": False,
            "error": "Authentication service temporarily unavailable (Firestore quota/network). Please retry in a few minutes."
        }

    return {
        "success": False,
        "error": "Login failed"
    }


@app.get("/api/auth/session/{user_id}")
async def validate_session(user_id: str):
    """
    Validate session and get fresh user data.

    Called by frontend to refresh user data (e.g., after permission changes).
    SECURITY NOTE: This endpoint returns user data by user_id without verifying
    the caller. In production, add JWT/session verification so callers can only
    request their own user_id. Frontend currently sends only its own id from localStorage.
    """
    try:
        if AUTH_FALLBACK_ENABLED and user_id == AUTH_FALLBACK_USER_ID:
            return {
                "success": True,
                "user": _build_auth_fallback_user(AUTH_FALLBACK_EMAIL),
            }

        # Run sync Firestore access off the event loop with timeout
        user = await asyncio.wait_for(
            asyncio.to_thread(user_service.get_user_by_id, user_id),
            timeout=AUTH_SESSION_TIMEOUT_SECONDS
        )

        if not user:
            return {
                "success": False,
                "error": "User not found"
            }

        # Check if user is still active
        if user.get('status') != 'active':
            return {
                "success": False,
                "error": f"Account is {user.get('status', 'inactive')}"
            }

        # Sanitize (fast, in-memory - no Firestore)
        sanitized = user_service._sanitize_user(user)
        return {
            "success": True,
            "user": sanitized
        }
    except asyncio.TimeoutError:
        print(f"[auth_api] session: TIMEOUT after {AUTH_SESSION_TIMEOUT_SECONDS}s for user_id={user_id}", flush=True)
        return {
            "success": False,
            "error": f"Session validation timeout ({AUTH_SESSION_TIMEOUT_SECONDS}s). Please retry."
        }
    except Exception as e:
        print(f"[auth_api] session: Session validation error: {e}", flush=True)
        return {
            "success": False,
            "error": "Session validation failed"
        }


@app.post("/api/auth/change-password")
async def change_password(request: ChangePasswordRequest):
    """
    Change user's password

    Requires current password for verification
    """
    try:
        success = user_service.change_password(
            request.user_id,
            request.current_password,
            request.new_password
        )

        if success:
            return {
                "success": True,
                "message": "Password changed successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to change password"
            }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"Change password error: {e}")
        return {
            "success": False,
            "error": "Failed to change password"
        }


# ==========================================
# User Management Endpoints
# ==========================================

@app.get("/api/auth/users")
async def get_users():
    """
    Get all dashboard users (without passwords)

    Admin only endpoint
    """
    try:
        users = user_service.get_all_users()
        return {
            "success": True,
            "users": users
        }
    except Exception as e:
        print(f"Get users error: {e}")
        return {
            "success": False,
            "error": "Failed to fetch users"
        }


@app.post("/api/auth/users")
async def create_user(request: CreateUserRequest, created_by: Optional[str] = None):
    """
    Create a new dashboard user

    Admin only endpoint - no self-registration
    """
    try:
        user_data = {
            "email": request.email,
            "password": request.password,
            "name": request.name,
            "role": request.role,
            "permissions": request.permissions,
            "status": request.status
        }

        user = user_service.create_user(user_data, created_by)

        return {
            "success": True,
            "user": user,
            "message": "User created successfully"
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"Create user error: {e}")
        return {
            "success": False,
            "error": "Failed to create user"
        }


@app.put("/api/auth/users/{user_id}")
async def update_user(user_id: str, request: UpdateUserRequest):
    """
    Update a dashboard user

    Admin only endpoint
    """
    try:
        updates = {}

        if request.name is not None:
            updates['name'] = request.name
        if request.role is not None:
            updates['role'] = request.role
        if request.permissions is not None:
            updates['permissions'] = request.permissions
        if request.status is not None:
            updates['status'] = request.status
        if request.password is not None:
            updates['password'] = request.password

        user = user_service.update_user(user_id, updates)

        return {
            "success": True,
            "user": user,
            "message": "User updated successfully"
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"Update user error: {e}")
        return {
            "success": False,
            "error": "Failed to update user"
        }


@app.delete("/api/auth/users/{user_id}")
async def delete_user(user_id: str):
    """
    Delete a dashboard user

    Admin only endpoint
    """
    try:
        success = user_service.delete_user(user_id)

        if success:
            return {
                "success": True,
                "message": "User deleted successfully"
            }
        else:
            return {
                "success": False,
                "error": "Failed to delete user"
            }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"Delete user error: {e}")
        return {
            "success": False,
            "error": "Failed to delete user"
        }
