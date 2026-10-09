"""Reject an assignee who is not an active member of the tenant."""

from __future__ import annotations

from services.requests.service import CustomerRequestsError


def assignee_is_member(tenant_id: str, user_id: str) -> bool:
    try:
        from services.team.user_service import UserService

        user = UserService().get_user_by_id(user_id)
    except Exception:
        return False
    if not isinstance(user, dict):
        return False
    if str(user.get("status") or "") != "active":
        return False
    owner = str(user.get("tenant_id") or user.get("tenantId") or "")
    return owner == tenant_id


def assert_assignee(tenant_id: str, user_id: str) -> None:
    if not assignee_is_member(tenant_id, user_id):
        raise CustomerRequestsError(
            "ASSIGNEE_NOT_MEMBER",
            "That person is not an active member of this business.",
            http_status=400,
        )
