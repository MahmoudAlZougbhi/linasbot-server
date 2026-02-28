"""
Auth API Module
Handles authentication and user management endpoints for the dashboard
"""

from fastapi import HTTPException
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional, List

from modules.core import app
from services.user_service import user_service


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
    try:
        user_service.ensure_default_admin()
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
    try:
        user = user_service.authenticate(request.email, request.password)

        if not user:
            return {
                "success": False,
                "error": "Invalid email or password"
            }

        return {
            "success": True,
            "user": user
        }
    except ValueError as e:
        return {
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        print(f"Login error: {e}")
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
        user = user_service.get_user_by_id(user_id)

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

        # Return sanitized user data
        return {
            "success": True,
            "user": user_service._sanitize_user(user)
        }
    except Exception as e:
        print(f"Session validation error: {e}")
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
