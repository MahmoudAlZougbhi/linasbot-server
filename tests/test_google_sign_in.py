"""Unit tests for Google ID token verification + duplicate-email policy."""

from __future__ import annotations

import time
from typing import Any
from unittest import mock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services import google_sign_in_service as gsi


@pytest.fixture()
def rsa_pair() -> tuple[Any, dict[str, Any]]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    numbers = public.public_numbers()

    def _b64url_uint(val: int) -> str:
        length = (val.bit_length() + 7) // 8
        return jwt.utils.base64url_encode(val.to_bytes(length, "big")).decode("ascii")

    jwk = {
        "kty": "RSA",
        "kid": "test-google-kid",
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
    }
    return private, jwk


def _mint(private: Any, *, aud: str, email: str = "user@example.com", email_verified: bool = True) -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "aud": aud,
            "sub": "google-sub-1",
            "email": email,
            "email_verified": email_verified,
            "name": "Test User",
            "iat": now,
            "exp": now + 600,
        },
        private,
        algorithm="RS256",
        headers={"kid": "test-google-kid"},
    )


def test_verify_google_id_token_ok(rsa_pair: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    private, jwk = rsa_pair
    aud = "client.apps.googleusercontent.com"
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", aud)
    gsi.reset_jwks_cache_for_tests()
    with mock.patch.object(gsi, "get_google_jwks", return_value={"keys": [jwk]}):
        claims = gsi.verify_identity_token(_mint(private, aud=aud))
    assert claims["sub"] == "google-sub-1"
    assert claims["email"] == "user@example.com"
    assert claims["email_verified"] is True


def test_verify_rejects_unverified_email(rsa_pair: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    private, jwk = rsa_pair
    aud = "client.apps.googleusercontent.com"
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", aud)
    gsi.reset_jwks_cache_for_tests()
    with mock.patch.object(gsi, "get_google_jwks", return_value={"keys": [jwk]}):
        with pytest.raises(gsi.GoogleSignInError, match="not verified"):
            gsi.verify_identity_token(_mint(private, aud=aud, email_verified=False))


def test_verify_rejects_bad_audience(rsa_pair: tuple[Any, dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    private, jwk = rsa_pair
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_IDS", "expected-client")
    gsi.reset_jwks_cache_for_tests()
    with mock.patch.object(gsi, "get_google_jwks", return_value={"keys": [jwk]}):
        with pytest.raises(gsi.GoogleSignInError):
            gsi.verify_identity_token(_mint(private, aud="other-client"))


def test_mobile_google_sign_in_link_required(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules import google_auth_api as api

    async def _run() -> None:
        monkeypatch.setattr(
            api,
            "verify_identity_token",
            lambda *_a, **_k: {
                "sub": "g-sub",
                "email": "taken@example.com",
                "email_verified": True,
                "name": "Taken",
            },
        )
        monkeypatch.setattr(api, "find_by_google_sub", lambda _s: None)
        monkeypatch.setattr(
            api.user_service,
            "get_user_by_email",
            lambda _e: {"id": "u1", "email": "taken@example.com", "status": "active"},
        )
        body = api.GoogleSignInRequest(identity_token="x" * 20)
        with pytest.raises(Exception) as ei:
            await api.mobile_google_sign_in(body)
        exc = ei.value
        assert getattr(exc, "status_code", None) == 409
        detail = getattr(exc, "detail", {})
        assert isinstance(detail, dict)
        assert detail.get("code") == "link_required"

    import asyncio

    asyncio.run(_run())
