"""Platform Owner user administration. Session/auth primitives stay in Dashboard/Team."""

from __future__ import annotations

from typing import Any

from services.dashboard.dashboard_session_service import session_service
from services.team.platform_owner_service import platform_owner_service
from services.team.tenant_custom_roles import tenant_custom_roles
from services.team.user_service import user_service


def update_platform_user(
    *,
    actor_user_id: str,
    user_id: str,
    status: str | None = None,
    role: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    target = user_service.get_user_by_id(user_id)
    if target is None:
        raise LookupError("User not found")
    if str(target.get("role") or "").lower() == "platform_owner":
        raise PermissionError("Platform-owner accounts are CLI-managed")
    updates: dict[str, Any] = {}
    if status is not None:
        normalized = status.strip().lower()
        if normalized not in {"active", "blocked"}:
            raise ValueError("Status must be active or blocked")
        updates["status"] = normalized
    if role is not None:
        tenant_id = str(target.get("tenantId") or "").strip()
        updates["role"] = role
        updates["_custom_role_ids"] = tenant_custom_roles.role_ids(tenant_id)
    if password is not None:
        updates["password"] = password
    if not updates:
        raise ValueError("No supported changes supplied")
    user = user_service.update_user(user_id, updates)
    if user is None:
        raise LookupError("User not found")
    session_service.revoke_all_for_user(user_id)
    platform_owner_service.log_action(
        actor_user_id=actor_user_id,
        action="update_user",
        tenant_id=str(target.get("tenantId") or ""),
        details={"user_id": user_id, "fields": sorted(k for k in updates if not k.startswith("_"))},
    )
    return user
