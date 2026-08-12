"""Permission helpers for Customer Requests APIs."""

from __future__ import annotations

from fastapi import HTTPException, Request

from modules.api_security import require_permission, user_has_permission
from services.dashboard_session_service import SessionRecord
from services.requests.constants import (
    PERM_REQUESTS,
    PERM_REQUESTS_MANAGE,
    PERM_REQUESTS_MANUAL_CHAT,
    PERM_REQUESTS_NOTIFY,
    PERM_REQUESTS_SENSITIVE,
)


def require_requests_view(request: Request) -> SessionRecord:
    return require_permission(request, PERM_REQUESTS)


def require_requests_manage(request: Request) -> SessionRecord:
    session = require_permission(request, PERM_REQUESTS)
    if not user_has_permission(session, PERM_REQUESTS_MANAGE):
        raise HTTPException(status_code=403, detail="requestsManage permission required")
    return session


def require_requests_notify(request: Request) -> SessionRecord:
    session = require_permission(request, PERM_REQUESTS)
    if not user_has_permission(session, PERM_REQUESTS_NOTIFY):
        raise HTTPException(status_code=403, detail="requestsNotify permission required")
    return session


def require_requests_manual_chat(request: Request) -> SessionRecord:
    session = require_permission(request, PERM_REQUESTS)
    if not user_has_permission(session, PERM_REQUESTS_MANUAL_CHAT):
        raise HTTPException(status_code=403, detail="requestsManualChat permission required")
    return session


def can_view_sensitive(session: SessionRecord) -> bool:
    return user_has_permission(session, PERM_REQUESTS_SENSITIVE)
