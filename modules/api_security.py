"""
Deny-by-default API authentication, CSRF, rate limits, and RBAC.

Public exceptions are intentionally minimal: health/ready + auth login only.
Logout requires a session + CSRF (not public). First-admin provisioning is offline CLI only.
Provider webhooks live outside /api/* and are handled separately.
"""

from __future__ import annotations

import hmac
import os
import re
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from services.auth_rate_limits import auth_rate_limit_rules, check_rate_limit, client_ip
from services.dashboard_session_service import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    SessionRecord,
    session_service,
)
from services.product_features import DISABLED_PRODUCT_MESSAGE, is_disabled_api_path

# Re-export for callers that historically imported from this module.
_client_ip = client_ip

__all__ = (
    "DashboardAuthMiddleware",
    "_client_ip",
    "auth_rate_limit_rules",
    "check_rate_limit",
    "client_ip",
    "get_request_session",
    "is_platform_owner",
    "is_production_env",
    "is_public_api",
    "is_social_user_id",
    "reject_social_operator_mutation",
    "require_permission",
    "require_platform_owner",
    "require_session",
    "required_permission_for",
    "resolve_permissions",
    "user_has_permission",
)

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
    "contentPublish",
    "activityFlow",
    "requests",
    "requestsManage",
    "requestsNotify",
    "requestsManualChat",
    "requestsSensitive",
}

SYSTEM_ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "admin": {k: True for k in PERMISSION_KEYS},
    "platform_owner": {k: True for k in PERMISSION_KEYS},
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
        "contentPublish": False,
        "activityFlow": True,
        "requests": True,
        "requestsManage": True,
        "requestsNotify": True,
        "requestsManualChat": True,
        "requestsSensitive": False,
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
        "contentPublish": False,
        "activityFlow": True,
        "requests": False,
        "requestsManage": False,
        "requestsNotify": False,
        "requestsManualChat": False,
        "requestsSensitive": False,
    },
}


def is_platform_owner(session: SessionRecord) -> bool:
    return (session.role or "").strip().lower() == "platform_owner"


def require_platform_owner(request: Request) -> SessionRecord:
    session = require_session(request)
    if not is_platform_owner(session):
        raise HTTPException(status_code=403, detail="Platform owner role required")
    return session


def is_production_env() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
    return env in {"prod", "production"}


def resolve_permissions(role: str, custom: dict[str, bool] | None) -> dict[str, bool]:
    base = dict(SYSTEM_ROLE_PERMISSIONS.get(role) or SYSTEM_ROLE_PERMISSIONS["viewer"])
    if role in {"admin", "platform_owner"}:
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
_PUBLIC_EXACT: set[tuple[str, str]] = {
    ("GET", "/api/health"),
    ("GET", "/api/ready"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/forgot-password"),
    ("POST", "/api/auth/reset-password"),
    ("POST", "/api/auth/verify-email"),
    ("POST", "/api/auth/resend-verification"),
    ("GET", "/api/billing/packages"),
    ("GET", "/api/public/plans"),
    ("POST", "/api/billing/stripe/webhook"),
    ("POST", "/api/auth/mobile/login"),
    ("POST", "/api/auth/mobile/refresh"),
    ("GET", "/api/queue/ready"),
    ("POST", "/api/entitlements/apple/notifications"),
    ("POST", "/api/entitlements/google/notifications"),
}

# Prefix public (rare) — guest sales chat is intentionally unauthenticated + rate-limited.
_PUBLIC_PREFIX: tuple[str, ...] = ("/api/guest-ai/",)


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


def required_permission_for(method: str, path: str) -> str | None:
    """
    Return permission key required for path, or None if authenticated-any is enough.
    """
    p = _normalize_path(path)

    if p.startswith("/api/auth/users"):
        return "userManagement"
    if p.startswith("/api/auth/"):
        return None  # authenticated self-service (session/me/change-password/logout)
    if p.startswith("/api/billing/"):
        return None  # session-scoped wallet; admin-credit checks role/tenant internally

    if p.startswith("/api/analytics") or p == "/api/stats":
        return "analytics"
    if p.startswith("/api/flow"):
        return "activityFlow"
    if p.startswith("/api/live-chat") or p.startswith("/api/chat-history"):
        return "liveChat"
    if p.startswith("/api/requests"):
        return "requests"
    if p.startswith("/api/owner-notifications"):
        return "liveChat"
    if p.startswith("/api/smart-messaging"):
        return "smartMessaging"
    if p.startswith("/api/settings"):
        return "settings"
    if p.startswith("/api/training-files") or p.startswith("/api/instructions"):
        return "training"
    if p.startswith("/api/content-files") or p.startswith("/api/retrieval-debug"):
        return "contentManagers"
    if p.startswith("/api/cm"):
        # Publish / rollback require contentPublish; everything else (meta/draft/validate/
        # versions list/preview-packet/local-qa bridge) uses contentManagers.
        if p == "/api/cm/publish" or p.endswith("/rollback"):
            return "contentPublish"
        if p.startswith("/api/cm/local-qa"):
            return "contentManagers"
        return "contentManagers"
    # Live Chat FAQ correction (save-all-languages) — operators need liveChat, not training.
    if p.startswith("/api/faq/"):
        return "liveChat"
    if p.startswith("/api/local-qa") or p.startswith("/api/qa") or p.startswith("/api/training"):
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


def get_request_session(request: Request) -> SessionRecord | None:
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
    async def dispatch(self, request: Request, call_next: Any) -> Any:
        path = _normalize_path(request.url.path)
        method = request.method.upper()

        # Non-API paths: still block docs in production
        if path in {"/docs", "/redoc", "/openapi.json"}:
            if is_production_env() or os.getenv("DISABLE_API_DOCS", "").lower() in {"1", "true", "yes"}:
                return JSONResponse(status_code=404, content={"detail": "Not found"})

        if not path.startswith("/api/"):
            return await call_next(request)

        # Attach session if present (Bearer preferred; cookie fallback)
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization") or ""
        bearer_token: str | None = None
        used_bearer = False
        if auth_header.lower().startswith("bearer "):
            bearer_token = auth_header[7:].strip() or None
        if bearer_token:
            session = session_service.get_valid_session(bearer_token)
            used_bearer = session is not None
        else:
            cookie = request.cookies.get(SESSION_COOKIE_NAME)
            session = session_service.get_valid_session(cookie)
        request.state.dashboard_session = session
        request.state.auth_via_bearer = used_bearer

        limited = await check_rate_limit(request, path)
        if limited is not None:
            return limited

        if is_public_api(method, path):
            return await call_next(request)

        if session is None:
            return JSONResponse(
                status_code=401,
                content={"success": False, "error": "Authentication required"},
            )

        # Wave 1: legacy product modules are disabled for ALL tenants (including linas).
        # Handlers remain in the repo but normal authenticated access is blocked.
        if is_disabled_api_path(path):
            return JSONResponse(
                status_code=403,
                content={
                    "success": False,
                    "error": DISABLED_PRODUCT_MESSAGE,
                    "code": "PRODUCT_MODULE_DISABLED",
                },
            )

        # The legacy dashboard control planes still operate on Lina's production
        # stores. External App B tenants are deliberately fail-closed to every
        # legacy API until that surface has an explicit tenant-aware query path.
        # Their self-service surface is Meta connection management, Content
        # Management (tenant-scoped drafts/publish), and authentication.
        if session.tenant_id != "linas" and not (
            path.startswith("/api/auth/")
            or path.startswith("/api/meta/connections")
            or path.startswith("/api/cm")
            or path.startswith("/api/faq/")
            or path.startswith("/api/billing/")
            or path.startswith("/api/owner-ai/")
            or path.startswith("/api/mobile/")
            or path.startswith("/api/entitlements/")
            or path.startswith("/api/creative/")
            or path.startswith("/api/schedule/")
            or path.startswith("/api/platform/")
            or path.startswith("/api/safety/")
            or path.startswith("/api/queue/")
            or path.startswith("/api/entitlements/")
        ):
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Tenant-isolated API unavailable"},
            )

        # CSRF for cookie-authenticated mutations only (Bearer mobile clients skip CSRF)
        if method in {"POST", "PUT", "PATCH", "DELETE"} and not used_bearer:
            header = request.headers.get(CSRF_HEADER_NAME) or request.headers.get(CSRF_HEADER_NAME.lower())
            csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME)
            if not header or not csrf_cookie or not session.csrf_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "CSRF validation failed"},
                )
            if not hmac.compare_digest(header, session.csrf_token) or not hmac.compare_digest(
                csrf_cookie, session.csrf_token
            ):
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


_SOCIAL_USER_RE = re.compile(
    r"^(?:[a-z0-9][a-z0-9_-]{0,63}:)?(?:instagram|facebook):",
    re.I,
)


def is_social_user_id(user_id: str | None) -> bool:
    if not user_id:
        return False
    return bool(_SOCIAL_USER_RE.match(str(user_id).strip()))


def reject_social_operator_mutation(user_id: str | None, channel: str | None = None) -> None:
    """Raise 403 if operator mutation targets Instagram/Facebook conversation."""
    ch = (channel or "").strip().lower()
    if ch in {"instagram", "facebook"} or is_social_user_id(user_id):
        raise HTTPException(
            status_code=403,
            detail="Operator mutations are not allowed for Instagram/Facebook conversations",
        )
