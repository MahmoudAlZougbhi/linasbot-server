"""Custom role catalog for tenant user management."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from pydantic import BaseModel

from modules.api_security import require_permission
from modules.core import app
from services.tenant_custom_roles import system_role_payloads, tenant_custom_roles


class CreateRoleRequest(BaseModel):
    name: str
    permissions: dict[str, bool] | None = None


@app.get("/api/auth/users/roles")
async def list_user_roles(request: Request) -> Any:
    session = require_permission(request, "userManagement")
    try:
        custom = tenant_custom_roles.list_roles(session.tenant_id)
        return {"success": True, "roles": [*system_role_payloads(), *custom]}
    except Exception as exc:
        print(f"List roles error: {exc}")
        return {"success": False, "error": "Failed to fetch roles"}


@app.post("/api/auth/users/roles")
async def create_user_role(body: CreateRoleRequest, request: Request) -> Any:
    session = require_permission(request, "userManagement")
    try:
        role = tenant_custom_roles.create_role(session.tenant_id, body.name, body.permissions)
        return {"success": True, "role": role}
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:
        print(f"Create role error: {exc}")
        raise HTTPException(status_code=500, detail="Failed to create role") from exc
