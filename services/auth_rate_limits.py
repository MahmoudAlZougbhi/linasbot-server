"""Trusted client IP + auth rate-limit rule builders (Redis/file/memory limiter)."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from services.rate_limit_service import rate_limit_service

_SENSITIVE_MUTATION_PREFIXES = (
    "/api/smart-messaging/send",
    "/api/smart-messaging/campaigns",
    "/api/smart-messaging/toggle",
    "/api/live-chat/send-message",
    "/api/live-chat/takeover",
    "/api/debug/",
    "/api/auth/login",
    "/api/auth/register",
    "/api/auth/change-password",
    "/api/auth/request-email-change",
    "/api/auth/mobile/login",
    "/api/auth/mobile/refresh",
)

_AUTH_IDENTIFIER_PATHS = frozenset(
    {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/forgot-password",
        "/api/auth/reset-password",
        "/api/auth/verify-email",
        "/api/auth/resend-verification",
        "/api/auth/request-email-change",
        "/api/auth/confirm-email-change",
        "/api/auth/mobile/login",
        "/api/auth/mobile/refresh",
    }
)


def _direct_client_host(request: Request) -> str:
    if request.client:
        return request.client.host or "unknown"
    return "unknown"


def client_ip(request: Request) -> str:
    """
    Client IP for rate limiting / abuse controls.

    Do **not** trust leftmost ``X-Forwarded-For`` from clients (spoofable).
    Nginx sets ``X-Real-IP`` to ``$remote_addr`` (the socket peer nginx saw).

    ``TRUSTED_PROXY_MODE`` (optional):
      - unset / ``x-real-ip`` (default): prefer ``X-Real-IP``, else ``request.client.host``
      - ``direct``: always ``request.client.host`` (ignore forwarded headers)
    """
    mode = (os.getenv("TRUSTED_PROXY_MODE") or "x-real-ip").strip().lower()
    if mode == "direct":
        return _direct_client_host(request)
    real_ip = (request.headers.get("x-real-ip") or "").strip()
    if real_ip:
        return real_ip.split(",")[0].strip() or _direct_client_host(request)
    return _direct_client_host(request)


def _normalize_email_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    if not email or "@" not in email or len(email) > 254:
        return None
    return email


def _token_fingerprint(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    token = value.strip()
    if len(token) < 8:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]


def _identifier_from_auth_body(path: str, body: dict[str, Any]) -> str | None:
    if path in {
        "/api/auth/login",
        "/api/auth/register",
        "/api/auth/forgot-password",
        "/api/auth/resend-verification",
        "/api/auth/request-email-change",
        "/api/auth/mobile/login",
    }:
        return _normalize_email_identifier(body.get("email") or body.get("new_email"))
    if path in {"/api/auth/reset-password", "/api/auth/verify-email", "/api/auth/confirm-email-change"}:
        return _token_fingerprint(body.get("token"))
    if path == "/api/auth/mobile/refresh":
        return _token_fingerprint(body.get("refresh_token"))
    return None


async def _peek_auth_identifier(request: Request, path: str) -> str | None:
    if path not in _AUTH_IDENTIFIER_PATHS:
        return None
    if request.method.upper() != "POST":
        return None
    try:
        raw = await request.body()
    except Exception:
        return None
    if not raw or len(raw) > 65536:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return _identifier_from_auth_body(path, payload)


def auth_rate_limit_rules(path: str, ip: str, identifier: str | None = None) -> list[tuple[str, int, int]]:
    """
    Return (key, limit, window_seconds) buckets for a path.

    Auth endpoints use IP + normalized identifier (email or token fingerprint)
    where applicable. Mobile login/refresh match or are stricter than dashboard login.
    """
    rules: list[tuple[str, int, int]] = []
    if path == "/api/auth/login":
        rules.append((f"login:{ip}", 10, 300))
        if identifier:
            rules.append((f"login:id:{identifier}", 5, 300))
    if path == "/api/auth/mobile/login":
        rules.append((f"mobile-login:{ip}", 10, 300))
        if identifier:
            rules.append((f"mobile-login:id:{identifier}", 5, 300))
    if path == "/api/auth/mobile/refresh":
        rules.append((f"mobile-refresh:{ip}", 10, 300))
        if identifier:
            rules.append((f"mobile-refresh:id:{identifier}", 5, 300))
    if path == "/api/auth/register":
        rules.append((f"register:{ip}", 5, 300))
        if identifier:
            rules.append((f"register:id:{identifier}", 5, 300))
    if path == "/api/auth/forgot-password":
        rules.append((f"forgot:{ip}", 5, 300))
        if identifier:
            rules.append((f"forgot:id:{identifier}", 5, 300))
    if path == "/api/auth/reset-password":
        rules.append((f"reset:{ip}", 10, 300))
        if identifier:
            rules.append((f"reset:id:{identifier}", 5, 300))
    if path == "/api/auth/verify-email":
        rules.append((f"verify:{ip}", 20, 300))
        if identifier:
            rules.append((f"verify:id:{identifier}", 10, 300))
    if path == "/api/auth/resend-verification":
        rules.append((f"resend-verify:{ip}", 5, 300))
        if identifier:
            rules.append((f"resend-verify:id:{identifier}", 5, 300))
    if path == "/api/auth/request-email-change":
        rules.append((f"email-change:{ip}", 5, 300))
        if identifier:
            rules.append((f"email-change:id:{identifier}", 5, 300))
    if path == "/api/auth/confirm-email-change":
        rules.append((f"email-change-confirm:{ip}", 10, 300))
        if identifier:
            rules.append((f"email-change-confirm:id:{identifier}", 5, 300))
    if path == "/api/auth/change-password":
        rules.append((f"pw:{ip}", 10, 300))
    if path.startswith("/api/guest-ai/"):
        rules.append((f"guest-ai:{ip}", 60, 300))
    if any(path.startswith(p) for p in _SENSITIVE_MUTATION_PREFIXES):
        rules.append((f"mut:{ip}:{path.split('?')[0]}", 60, 60))
    return rules


async def check_rate_limit(request: Request, path: str) -> JSONResponse | None:
    ip = client_ip(request)
    identifier = await _peek_auth_identifier(request, path)
    for key, limit, window in auth_rate_limit_rules(path, ip, identifier):
        allowed, retry = rate_limit_service.hit(key, limit=limit, window_seconds=window)
        if not allowed:
            if rate_limit_service.last_deny_reason == "backend_unavailable":
                return JSONResponse(
                    status_code=503,
                    content={
                        "success": False,
                        "error": "Rate limit service unavailable",
                        "retry_after": retry,
                    },
                    headers={"Retry-After": str(retry)},
                )
            return JSONResponse(
                status_code=429,
                content={"success": False, "error": "Rate limit exceeded", "retry_after": retry},
                headers={"Retry-After": str(retry)},
            )
    return None
