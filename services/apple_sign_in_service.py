"""Verify Sign in with Apple identity tokens (ES256 + Apple JWKS)."""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import jwt

from services.apple_secrets import apple_bundle_id

APPLE_ISS = "https://appleid.apple.com"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
_JWKS_TTL_SECONDS = 3600

_lock = threading.RLock()
_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0

PRIVATE_RELAY_SUFFIX = "@privaterelay.appleid.com"


class AppleSignInError(ValueError):
    """Identity token validation failed."""


def is_private_relay_email(email: str | None) -> bool:
    e = (email or "").strip().lower()
    return bool(e) and e.endswith(PRIVATE_RELAY_SUFFIX)


def _fetch_jwks_uncached() -> dict[str, Any]:
    req = urllib.request.Request(
        APPLE_JWKS_URL,
        headers={"Accept": "application/json", "User-Agent": "linasbot-server/apple-sign-in"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AppleSignInError("Unable to fetch Apple JWKS") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AppleSignInError("Invalid Apple JWKS payload") from exc
    if not isinstance(data, dict) or not isinstance(data.get("keys"), list):
        raise AppleSignInError("Apple JWKS missing keys")
    return data


def get_apple_jwks(*, force_refresh: bool = False) -> dict[str, Any]:
    global _jwks_cache, _jwks_fetched_at
    now = time.time()
    with _lock:
        if (
            not force_refresh
            and _jwks_cache is not None
            and (now - _jwks_fetched_at) < _JWKS_TTL_SECONDS
        ):
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
        raise AppleSignInError("Malformed identity token header") from exc
    kid = str(header.get("kid") or "").strip()
    alg = str(header.get("alg") or "").strip()
    if alg != "ES256":
        raise AppleSignInError("Unsupported identity token algorithm")
    if not kid:
        raise AppleSignInError("Identity token missing kid")

    jwks = get_apple_jwks()
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if not isinstance(keys, list):
        raise AppleSignInError("Apple JWKS unavailable")

    for key_dict in keys:
        if isinstance(key_dict, dict) and str(key_dict.get("kid") or "") == kid:
            try:
                return jwt.PyJWK.from_dict(key_dict).key
            except Exception as exc:
                raise AppleSignInError("Unable to parse Apple JWK") from exc

    # One forced refresh in case of key rotation.
    jwks = get_apple_jwks(force_refresh=True)
    keys = jwks.get("keys") if isinstance(jwks, dict) else None
    if isinstance(keys, list):
        for key_dict in keys:
            if isinstance(key_dict, dict) and str(key_dict.get("kid") or "") == kid:
                try:
                    return jwt.PyJWK.from_dict(key_dict).key
                except Exception as exc:
                    raise AppleSignInError("Unable to parse Apple JWK") from exc
    raise AppleSignInError("Apple signing key not found for kid")


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
    """
    Validate Apple identity token.

    Returns claims plus normalized email fields. Name is never in the token
    (client sends it on first login only).
    """
    token = (identity_token or "").strip()
    if not token:
        raise AppleSignInError("identity_token required")

    audience = apple_bundle_id()
    key = _signing_key_for_token(token)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            audience=audience,
            issuer=APPLE_ISS,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.exceptions.ExpiredSignatureError as exc:
        raise AppleSignInError("Identity token expired") from exc
    except jwt.exceptions.InvalidAudienceError as exc:
        raise AppleSignInError("Identity token audience mismatch") from exc
    except jwt.exceptions.InvalidIssuerError as exc:
        raise AppleSignInError("Identity token issuer mismatch") from exc
    except jwt.exceptions.PyJWTError as exc:
        raise AppleSignInError("Identity token signature or claims invalid") from exc

    if not isinstance(claims, dict):
        raise AppleSignInError("Identity token claims invalid")

    sub = str(claims.get("sub") or "").strip()
    if not sub:
        raise AppleSignInError("Identity token missing sub")

    if nonce is not None and str(nonce).strip():
        # Apple puts SHA-256(raw_nonce) (hex) in the identity token.
        expected = hashlib.sha256(str(nonce).strip().encode("utf-8")).hexdigest()
        token_nonce = str(claims.get("nonce") or "").strip()
        if not token_nonce or token_nonce.lower() != expected.lower():
            raise AppleSignInError("Identity token nonce mismatch")

    email_raw = claims.get("email")
    email = str(email_raw).strip().lower() if email_raw else None
    email_verified = _claim_bool(claims.get("email_verified"))
    is_private_email = _claim_bool(claims.get("is_private_email"))
    if email and is_private_email is None:
        is_private_email = is_private_relay_email(email)
    if email and is_private_relay_email(email):
        is_private_email = True

    return {
        "sub": sub,
        "email": email,
        "email_verified": email_verified,
        "is_private_email": is_private_email,
        "iss": claims.get("iss"),
        "aud": claims.get("aud"),
        "exp": claims.get("exp"),
        "iat": claims.get("iat"),
        "nonce": claims.get("nonce"),
        "raw_claims": claims,
    }
