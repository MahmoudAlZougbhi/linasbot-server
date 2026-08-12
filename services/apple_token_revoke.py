"""Sign in with Apple token exchange + revoke.

Uses AuthKey (.p8) from apple_secrets — never SubscriptionKey.
Never log tokens, authorization codes, or private key PEM.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import jwt

from services.apple_secrets import (
    apple_bundle_id,
    apple_sign_in_key_id,
    apple_sign_in_key_path,
    apple_team_id,
    read_private_key_pem,
)

logger = logging.getLogger(__name__)

APPLE_TOKEN_URL = "https://appleid.apple.com/auth/token"
APPLE_REVOKE_URL = "https://appleid.apple.com/auth/revoke"
APPLE_AUD = "https://appleid.apple.com"
_CLIENT_SECRET_TTL = 3600
_HTTP_TIMEOUT = 15


class AppleTokenRevokeError(RuntimeError):
    """Apple token / revoke API failure (no secrets in message)."""


def build_client_secret(*, ttl_seconds: int = _CLIENT_SECRET_TTL) -> str:
    """ES256 client_secret JWT for Sign in with Apple (AuthKey path only)."""
    key_path = apple_sign_in_key_path()
    key_id = apple_sign_in_key_id()
    team_id = apple_team_id()
    client_id = apple_bundle_id()
    if not key_id or not team_id or not client_id:
        raise AppleTokenRevokeError("Apple Sign in client credentials incomplete")
    try:
        pem = read_private_key_pem(key_path)
    except (OSError, ValueError, FileNotFoundError) as exc:
        logger.info("apple_client_secret key_path_unreadable path=%s", key_path)
        raise AppleTokenRevokeError("Apple Sign in AuthKey unavailable") from exc

    now = int(time.time())
    ttl = max(60, min(int(ttl_seconds), 15777000))
    payload = {
        "iss": team_id,
        "iat": now,
        "exp": now + ttl,
        "aud": APPLE_AUD,
        "sub": client_id,
    }
    return jwt.encode(
        payload,
        pem,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id, "typ": "JWT"},
    )


def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "linasbot-server/apple-token-revoke",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read() if hasattr(exc, "read") else b""
        logger.info("apple_token_http status=%s url=%s", status, url.split("?")[0])
        raise AppleTokenRevokeError(f"Apple HTTP {status}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.info("apple_token_network err=%s url=%s", type(exc).__name__, url.split("?")[0])
        raise AppleTokenRevokeError("Apple network error") from exc

    if status >= 400:
        raise AppleTokenRevokeError(f"Apple HTTP {status}")
    if not raw:
        return {"ok": True, "status": status}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppleTokenRevokeError("Apple response not JSON") from exc
    if not isinstance(data, dict):
        raise AppleTokenRevokeError("Apple response invalid")
    return data


def exchange_authorization_code(code: str) -> dict[str, Any]:
    """Exchange authorization_code for tokens. Never log the code or tokens."""
    auth_code = (code or "").strip()
    if not auth_code:
        raise AppleTokenRevokeError("authorization_code required")
    fields = {
        "client_id": apple_bundle_id(),
        "client_secret": build_client_secret(),
        "code": auth_code,
        "grant_type": "authorization_code",
    }
    data = _post_form(APPLE_TOKEN_URL, fields)
    out: dict[str, Any] = {}
    for key in ("access_token", "refresh_token", "id_token", "token_type", "expires_in"):
        if key in data and data[key] is not None:
            out[key] = data[key]
    if not out.get("refresh_token") and not out.get("access_token"):
        raise AppleTokenRevokeError("Apple token response missing tokens")
    return out


def revoke_apple_token(token: str, token_type_hint: str = "refresh_token") -> dict[str, Any]:
    """POST auth/revoke. Never log the token."""
    value = (token or "").strip()
    if not value:
        raise AppleTokenRevokeError("token required")
    hint = (token_type_hint or "refresh_token").strip() or "refresh_token"
    if hint not in {"refresh_token", "access_token"}:
        hint = "refresh_token"
    fields = {
        "client_id": apple_bundle_id(),
        "client_secret": build_client_secret(),
        "token": value,
        "token_type_hint": hint,
    }
    data = _post_form(APPLE_REVOKE_URL, fields)
    logger.info("apple_token_revoked hint=%s", hint)
    return data if data else {"ok": True}
