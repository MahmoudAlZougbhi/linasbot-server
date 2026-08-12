"""Auth user-management endpoints (LOC split from auth_api)."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from modules.api_security import require_session
from modules.auth_api_common import CreateUserRequest, UpdateUserRequest
from modules.core import app
from services.dashboard_session_service import session_service
from services.user_service import user_service


@app.get("/api/auth/users")
async def get_users(request: Request) -> Any:
    session = require_session(request)
    try:
        users = [
            user for user in user_service.get_all_users() if str(user.get("tenantId") or "").strip() == session.tenant_id
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
    from services.entitlements_service import entitlements_store
    from services.membership.seats import SeatLimitExceeded, assert_can_add_seat

    ent = entitlements_store.get(session.tenant_id)
    if ent.plan_id in {"lite", "starter", "growth", "pro", "max"}:
        tenant_users = [
            user for user in user_service.get_all_users() if str(user.get("tenantId") or "").strip() == session.tenant_id
        ]
        non_owners = [
            u
            for u in tenant_users
            if str(u.get("role") or "").lower() != "owner" and str(u.get("status") or "active").lower() == "active"
        ]
        # No invitation subsystem on this spine yet — count active non-owners only.
        try:
            assert_can_add_seat(
                ent.plan_id,
                active_non_owner_members=len(non_owners),
                pending_invitations=0,
            )
        except SeatLimitExceeded as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    if target is None or str(target.get("tenantId") or "").strip() != session.tenant_id:
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
    if target is None or str(target.get("tenantId") or "").strip() != session.tenant_id:
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
