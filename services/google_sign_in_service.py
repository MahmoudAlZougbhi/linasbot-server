"""Verify Google Sign-In ID tokens (RS256 + Google JWKS)."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import jwt

GOOGLE_ISS = frozenset({"https://accounts.google.com", "accounts.google.com"})
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
_JWKS_TTL_SECONDS = 3600

_lock = threading.RLock()
_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0


class GoogleSignInError(ValueError):
    """Google identity token validation failed."""


def google_oauth_client_ids() -> list[str]:
    """Comma-separated client IDs allowed as token ``aud`` (iOS/Android/Web)."""
    raw = (os.getenv("GOOGLE_OAUTH_CLIENT_IDS") or os.getenv("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    return [p.strip() for p in raw.split(",") if p.strip()]


def _fetch_jwks_uncached() -> dict[str, Any]:
    req = urllib.request.Request(
        GOOGLE_JWKS_URL,
        headers={"Accept": "application/json", "User-Agent": "linasbot-server/google-sign-in"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise GoogleSignInError("Unable to fetch Google JWKS") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GoogleSignInError("Invalid Google JWKS payload") from exc
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise GoogleSignInError("Google JWKS missing keys")
    return data


def get_google_jwks(*, force_refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    with _lock:
        if not force_refresh and _jwks_cache is not None and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
            return _jwks_cache
    data = _fetch_jwks_uncached()
    with _lock:
        _jwks_cache = data
        _jwks_fetched_at = time.time()
        return data


def reset_jwks_cache_for_tests() -> None:
    global _jwks_cache, _jwks_fetched_at
    with _lock:
        _jwks_cache = None
        _jwks_fetched_at = 0.0


def _signing_key_for_token(identity_token: str) -> Any:
    try:
        header = jwt.get_unverified_header(identity_token)
    except jwt.exceptions.DecodeError as exc:
        raise GoogleSignInError("Malformed identity token header") from exc
    kid = str(header.get("kid") or "").strip()
    alg = str(header.get("alg") or "").strip()
    if alg != "RS256":
        raise GoogleSignInError("Unsupported identity token algorithm")
    if not kid:
        raise GoogleSignInError("Identity token missing kid")

    for force in (False, True):
        jwks = get_google_jwks(force_refresh=force)
        keys = jwks.get("keys") if isinstance(jwks, dict) else None
        if not isinstance(keys, list):
            continue
        for key_dict in keys:
            if isinstance(key_dict, dict) and str(key_dict.get("kid") or "") == kid:
                try:
                    return jwt.PyJWK.from_dict(key_dict).key
                except Exception as exc:
                    raise GoogleSignInError("Unable to parse Google JWK") from exc
        if force:
            break
    raise GoogleSignInError("Google signing key not found for kid")


def _claim_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    if s in {"true", "1", "yes"}:
        return True
    if s in {"false", "0", "no"}:
        return False
    return None


def verify_identity_token(identity_token: str, *, nonce: str | None = None) -> dict[str, Any]:
    """Validate Google ID token; require email_verified for first-party auth."""
    token = (identity_token or "").strip()
    if not token:
        raise GoogleSignInError("identity_token required")

    audiences = google_oauth_client_ids()
    if not audiences:
        raise GoogleSignInError("GOOGLE_OAUTH_CLIENT_IDS not configured")

    key = _signing_key_for_token(token)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=audiences,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.exceptions.ExpiredSignatureError as exc:
        raise GoogleSignInError("Identity token expired") from exc
    except jwt.exceptions.InvalidAudienceError as exc:
        raise GoogleSignInError("Identity token audience mismatch") from exc
    except jwt.exceptions.PyJWTError as exc:
        raise GoogleSignInError("Identity token signature or claims invalid") from exc

    if not isinstance(claims, dict):
        raise GoogleSignInError("Identity token claims invalid")

    iss = str(claims.get("iss") or "").strip()
    if iss not in GOOGLE_ISS:
        raise GoogleSignInError("Identity token issuer mismatch")

    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise GoogleSignInError("Identity token missing sub")

    if nonce is not None and str(nonce).strip():
        token_nonce = str(claims.get("nonce") or "").strip()
        if not token_nonce or token_nonce != str(nonce).strip():
            raise GoogleSignInError("Identity token nonce mismatch")

    email_raw = claims.get("email")
    email = str(email_raw).strip().lower() if email_raw else None
    email_verified = _claim_bool(claims.get("email_verified"))
    if email and email_verified is not True:
        raise GoogleSignInError("Google email not verified")

    name = str(claims.get("name") or "").strip() or None
    return {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
        "exp": claims.get("exp"),
        "iat": claims.get("iat"),
        "nonce": claims.get("nonce"),
        "raw_claims": claims,
    }
