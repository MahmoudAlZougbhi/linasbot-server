# -*- coding: utf-8 -*-
"""
Deny-by-default API authentication, CSRF, rate limits, and RBAC.

Public exceptions are intentionally minimal: health + auth login/logout bootstrap.
Provider webhooks live outside /api/* and are handled separately.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Set, Tuple

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services.dashboard_session_service import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SessionRecord,
    session_service,
)
from services.rate_limit_service import rate_limit_service


# Frontend-aligned permission keys
PERMISSION_KEYS = {
    "dashboard",
    "liveChat",
    "training",
    "testing",
    "analytics",
    "smartMessaging",
    "settings",
    "userManagement",
    "contentManagers",
    "activityFlow",
}

SYSTEM_ROLE_PERMISSIONS: Dict[str, Dict[str, bool]] = {
    "admin": {k: True for k in PERMISSION_KEYS},
    "operator": {
        "dashboard": True,
        "liveChat": True,
        "training": False,
        "testing": False,
        "analytics": True,
        "smartMessaging": True,
        "settings": False,
        "userManagement": False,
        "contentManagers": False,
        "activityFlow": True,
    },
    "viewer": {
        "dashboard": True,
        "liveChat": False,
        "training": False,
        "testing": False,
        "analytics": True,
        "smartMessaging": False,
        "settings": False,
        "userManagement": False,
        "contentManagers": False,
        "activityFlow": True,
    },
}


def is_production_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    return env in {"prod", "production"}


def resolve_permissions(role: str, custom: Optional[Dict[str, bool]]) -> Dict[str, bool]:
    base = dict(SYSTEM_ROLE_PERMISSIONS.get(role) or SYSTEM_ROLE_PERMISSIONS["viewer"])
    if role == "admin":
        return {k: True for k in PERMISSION_KEYS}
    if custom:
        for k, v in custom.items():
            if k in PERMISSION_KEYS:
                base[k] = bool(v)
    return base


def user_has_permission(session: SessionRecord, permission: str) -> bool:
    perms = resolve_permissions(session.role, session.permissions)
    return bool(perms.get(permission))


# Exact public API paths (method, path)
_PUBLIC_EXACT: Set[Tuple[str, str]] = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("POST", "/api/auth/bootstrap-admin"),
}

# Prefix public (rare)
_PUBLIC_PREFIX: Tuple[str, ...] = ()


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    if len(path) > 1 and path.endswith("/"):
        return path.rstrip("/")
    return path


def is_public_api(method: str, path: str) -> bool:
    m = method.upper()
    p = _normalize_path(path)
    if (m, p) in _PUBLIC_EXACT:
        return True
    for pref in _PUBLIC_PREFIX:
        if p.startswith(pref):
            return True
    return False


def required_permission_for(method: str, path: str) -> Optional[str]:
    """
    Return permission key required for path, or None if authenticated-any is enough.
    """
    p = _normalize_path(path)
    m = method.upper()

    if p.startswith("/api/auth/users"):
        return "userManagement"
    if p.startswith("/api/auth/"):
        return None  # authenticated self-service (session/me/change-password/logout)

    if p.startswith("/api/analytics") or p == "/api/stats":
        return "analytics"
    if p.startswith("/api/flow"):
        return "activityFlow"
    if p.startswith("/api/live-chat") or p.startswith("/api/chat-history"):
        return "liveChat"
    if p.startswith("/api/smart-messaging"):
        return "smartMessaging"
    if p.startswith("/api/settings"):
        return "settings"
    if p.startswith("/api/training-files") or p.startswith("/api/instructions"):
        return "training"
    if p.startswith("/api/content-files") or p.startswith("/api/retrieval-debug"):
        return "contentManagers"
    if p.startswith("/api/local-qa") or p.startswith("/api/faq") or p.startswith("/api/qa") or p.startswith("/api/training"):
        return "training"
    if p.startswith("/api/feedback"):
        return "training"
    if p.startswith("/api/test") or p.startswith("/api/switch-provider") or p.startswith("/api/debug"):
        return "testing"
    if p.startswith("/api/media"):
        return "liveChat"
    if p == "/api/health":
        return None
    # Default deny classifies unknown /api as settings-level (admin-ish) rather than open
    return "settings"


_SENSITIVE_MUTATION_PREFIXES = (
    "/api/smart-messaging/send",
    "/api/smart-messaging/campaigns",
    "/api/smart-messaging/toggle",
    "/api/live-chat/send-message",
    "/api/live-chat/takeover",
    "/api/debug/",
    "/api/auth/login",
    "/api/auth/change-password",
)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip() or "unknown"
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def check_rate_limit(request: Request, path: str) -> Optional[JSONResponse]:
    ip = _client_ip(request)
    rules = []
    if path == "/api/auth/login":
        rules.append((f"login:{ip}", 10, 300))
    if path == "/api/auth/change-password":
        rules.append((f"pw:{ip}", 10, 300))
    if any(path.startswith(p) for p in _SENSITIVE_MUTATION_PREFIXES):
        rules.append((f"mut:{ip}:{path.split('?')[0]}", 60, 60))
    for key, limit, window in rules:
        allowed, retry = rate_limit_service.hit(key, limit=limit, window_seconds=window)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Rate limit exceeded", "retry_after": retry},
                headers={"Retry-After": str(retry)},
            )
    return None


def get_request_session(request: Request) -> Optional[SessionRecord]:
    return getattr(request.state, "dashboard_session", None)


def require_session(request: Request) -> SessionRecord:
    session = get_request_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Authentication required")
    return session


def require_permission(request: Request, permission: str) -> SessionRecord:
    session = require_session(request)
    if not user_has_permission(session, permission):
        raise HTTPException(status_code=403, detail="Forbidden")
    return session


class DashboardAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = _normalize_path(request.url.path)
        method = request.method.upper()

        # Non-API paths: still block docs in production
        if path in {"/docs", "/redoc", "/openapi.json"}:
            if is_production_env() or os.getenv("DISABLE_API_DOCS", "").lower() in {"1", "true", "yes"}:
                return JSONResponse(status_code=404, content={"detail": "Not found"})

        if not path.startswith("/api/"):
            return await call_next(request)

        # Attach session if present (even for public routes)
        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        session = session_service.get_valid_session(cookie)
        request.state.dashboard_session = session

        limited = check_rate_limit(request, path)
        if limited is not None:
            return limited

        if is_public_api(method, path):
            return await call_next(request)

        if session is None:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Authentication required"},
            )

        # CSRF for cookie-authenticated mutations
        if method in {"POST", "PUT", "PATCH", "DELETE"}:
            header = request.headers.get(CSRF_HEADER_NAME) or request.headers.get(CSRF_HEADER_NAME.lower())
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
            if not header or not csrf_cookie or not session.csrf_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "CSRF validation failed"},
                )
            if header != session.csrf_token or csrf_cookie != session.csrf_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "CSRF validation failed"},
                )

        needed = required_permission_for(method, path)
        if needed and not user_has_permission(session, needed):
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Forbidden"},
            )

        return await call_next(request)


_SOCIAL_USER_RE = re.compile(r"^(instagram|facebook):", re.I)


def is_social_user_id(user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    return bool(_SOCIAL_USER_RE.match(str(user_id).strip()))


def reject_social_operator_mutation(user_id: Optional[str], channel: Optional[str] = None) -> None:
    """Raise 403 if operator mutation targets Instagram/Facebook conversation."""
    ch = (channel or "").strip().lower()
    if ch in {"instagram", "facebook"} or is_social_user_id(user_id):
        raise HTTPException(
            status_code=403,
            detail="Operator mutations are not allowed for Instagram/Facebook conversations",
        )
