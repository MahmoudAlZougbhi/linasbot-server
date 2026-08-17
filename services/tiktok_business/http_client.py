"""SSRF-safe TikTok Business API HTTP client. Never logs tokens."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from services.tiktok_business.config import (
    RETRYABLE_TIKTOK_CODES,
    TIKTOK_API_BASE,
    TIKTOK_API_HOST,
    TOKEN_EXPIRED_TIKTOK_CODES,
    get_tiktok_settings,
)
from services.tiktok_business.errors import TikTokApiError, TikTokNotConfiguredError

_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
_REDACT = frozenset({"access_token", "refresh_token", "client_secret", "auth_code", "code", "token"})


def _safe_url(path: str) -> str:
    cleaned = str(path or "").strip()
    if not cleaned.startswith("/") or ".." in cleaned or cleaned.startswith("//"):
        raise TikTokApiError("refusing unsafe TikTok API path", http_status=500)
    url = f"{TIKTOK_API_BASE}{cleaned}"
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != TIKTOK_API_HOST:
        raise TikTokApiError("refusing non-allowlisted TikTok host", http_status=500)
    return url


def _redact(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {k: ("[redacted]" if k.lower() in _REDACT else _redact(v)) for k, v in payload.items()}
    if isinstance(payload, list):
        return [_redact(item) for item in payload]
    return payload


def is_retryable(tiktok_code: int | None, http_status: int) -> bool:
    if http_status in {429, 500, 502, 503, 504}:
        return True
    return tiktok_code in RETRYABLE_TIKTOK_CODES


async def tiktok_request(
    *,
    method: str,
    path: str,
    access_token: str | None = None,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_tiktok_settings()
    if not settings.configured:
        raise TikTokNotConfiguredError("TikTok Business credentials are not configured")
    url = _safe_url(path)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if access_token:
        headers["Access-Token"] = access_token
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False) as client:
            response = await client.request(method.upper(), url, headers=headers, json=json_body, params=params)
    except httpx.HTTPError as exc:
        raise TikTokApiError(f"TikTok transport error: {type(exc).__name__}", retryable=True) from exc
    try:
        payload = response.json() if response.content else {}
    except ValueError as exc:
        raise TikTokApiError("TikTok returned non-JSON", retryable=is_retryable(None, response.status_code)) from exc
    if not isinstance(payload, dict):
        raise TikTokApiError("TikTok returned a non-object JSON body")
    code = payload.get("code")
    tiktok_code = int(code) if isinstance(code, int) else None
    request_id = str(payload.get("request_id") or "")
    if response.status_code >= 400 or (tiktok_code is not None and tiktok_code != 0):
        message = str(payload.get("message") or f"TikTok HTTP {response.status_code}")
        retryable = is_retryable(tiktok_code, response.status_code)
        expired = tiktok_code in TOKEN_EXPIRED_TIKTOK_CODES
        raise TikTokApiError(
            message,
            tiktok_code=tiktok_code,
            request_id=request_id,
            retryable=retryable or expired,
            http_status=401 if expired else (429 if tiktok_code == 40100 else 502),
        )
    data = payload.get("data")
    if data is None:
        return {"request_id": request_id}
    if not isinstance(data, dict):
        return {"request_id": request_id, "data": data}
    return {**data, "request_id": request_id}


def dump_safe(payload: dict[str, Any]) -> str:
    return json.dumps(_redact(payload), separators=(",", ":"), default=str)
