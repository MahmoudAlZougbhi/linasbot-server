"""Offline tests for Sign in with Apple token verify + identity store."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from fastapi import HTTPException
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services import apple_sign_in_service as sign_in  # noqa: E402
from services.apple_identity_service import (  # noqa: E402
    AppleIdentityError,
    find_by_apple_sub,
    get_or_create_app_account_token,
    link_apple_identity,
    unlink_apple_identity,
)
from services.apple_sign_in_service import (  # noqa: E402
    AppleSignInError,
    is_private_relay_email,
    nonce_matches,
    reset_jwks_cache_for_tests,
    verify_identity_token,
)


def _ephemeral_rs256() -> tuple[rsa.RSAPrivateKey, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    from jwt.algorithms import RSAAlgorithm

    jwk = json.loads(RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "test-kid-rs1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return private_key, jwk


def _ephemeral_es256() -> tuple[ec.EllipticCurvePrivateKey, dict[str, Any]]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    from jwt.algorithms import ECAlgorithm

    jwk = json.loads(ECAlgorithm.to_jwk(public_key))
    jwk["kid"] = "test-kid-es1"
    jwk["use"] = "sig"
    jwk["alg"] = "ES256"
    return private_key, jwk


def _mint_token(
    private_key: Any,
    *,
    alg: str = "RS256",
    kid: str = "test-kid-rs1",
    aud: str = "com.linasai.app",
    iss: str = "https://appleid.apple.com",
    sub: str = "apple-sub-1",
    exp_delta: int = 600,
    nonce: str | None = None,
    nonce_encoding: str = "hex",
    email: str | None = "user@example.com",
    extra: dict[str, Any] | None = None,
) -> str:
    now = int(time.time())
    payload: dict[str, Any] = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "iat": now,
        "exp": now + exp_delta,
    }
    if email is not None:
        payload["email"] = email
        payload["email_verified"] = "true"
    if nonce is not None:
        digest = hashlib.sha256(str(nonce).encode("utf-8")).digest()
        if nonce_encoding == "b64url":
            payload["nonce"] = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        else:
            payload["nonce"] = digest.hex()
    if extra:
        payload.update(extra)
    return jwt.encode(payload, private_key, algorithm=alg, headers={"kid": kid, "alg": alg})


@pytest.fixture()
def apple_jwks_rs(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    private_key, jwk = _ephemeral_rs256()
    reset_jwks_cache_for_tests()

    def _fake_fetch() -> dict[str, Any]:
        return {"keys": [jwk]}

    monkeypatch.setattr(sign_in, "_fetch_jwks_uncached", _fake_fetch)
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.linasai.app")
    yield private_key
    reset_jwks_cache_for_tests()


@pytest.fixture()
def apple_jwks_es(monkeypatch: pytest.MonkeyPatch) -> ec.EllipticCurvePrivateKey:
    private_key, jwk = _ephemeral_es256()
    reset_jwks_cache_for_tests()

    def _fake_fetch() -> dict[str, Any]:
        return {"keys": [jwk]}

    monkeypatch.setattr(sign_in, "_fetch_jwks_uncached", _fake_fetch)
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.linasai.app")
    yield private_key
    reset_jwks_cache_for_tests()


@pytest.fixture()
def pg_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'apple_auth.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


def test_is_private_relay_email() -> None:
    assert is_private_relay_email("abc@privaterelay.appleid.com") is True
    assert is_private_relay_email("user@example.com") is False
    assert is_private_relay_email(None) is False


def test_nonce_matches_hex_and_b64url() -> None:
    raw = "raw-nonce-xyz"
    hex_claim = hashlib.sha256(raw.encode()).hexdigest()
    b64_claim = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()).decode().rstrip("=")
    assert nonce_matches(raw_nonce=raw, token_nonce=hex_claim) is True
    assert nonce_matches(raw_nonce=raw, token_nonce=b64_claim) is True
    assert nonce_matches(raw_nonce=raw, token_nonce="nope") is False


def test_verify_identity_token_rs256_success(apple_jwks_rs: rsa.RSAPrivateKey) -> None:
    token = _mint_token(apple_jwks_rs, nonce="n-1", email="a@privaterelay.appleid.com")
    claims = verify_identity_token(token, nonce="n-1")
    assert claims["sub"] == "apple-sub-1"
    assert claims["email"] == "a@privaterelay.appleid.com"
    assert claims["is_private_email"] is True


def test_verify_identity_token_rs256_nonce_b64url(apple_jwks_rs: rsa.RSAPrivateKey) -> None:
    token = _mint_token(apple_jwks_rs, nonce="n-2", nonce_encoding="b64url")
    claims = verify_identity_token(token, nonce="n-2")
    assert claims["sub"] == "apple-sub-1"


def test_verify_identity_token_es256_still_accepted(apple_jwks_es: ec.EllipticCurvePrivateKey) -> None:
    token = _mint_token(
        apple_jwks_es,
        alg="ES256",
        kid="test-kid-es1",
        nonce="n-es",
    )
    claims = verify_identity_token(token, nonce="n-es")
    assert claims["sub"] == "apple-sub-1"


def test_verify_rejects_unsupported_alg(apple_jwks_rs: rsa.RSAPrivateKey) -> None:
    token = _mint_token(apple_jwks_rs)
    header_b64, payload_b64, sig = token.split(".")
    header = json.loads(base64.urlsafe_b64decode(header_b64 + "=="))
    header["alg"] = "HS256"
    new_header = base64.urlsafe_b64encode(json.dumps(header, separators=(",", ":")).encode()).decode().rstrip("=")
    bad = f"{new_header}.{payload_b64}.{sig}"
    with pytest.raises(AppleSignInError, match="algorithm"):
        verify_identity_token(bad)


def test_verify_identity_token_bad_aud(apple_jwks_rs: rsa.RSAPrivateKey) -> None:
    token = _mint_token(apple_jwks_rs, aud="com.other.app")
    with pytest.raises(AppleSignInError, match="audience"):
        verify_identity_token(token)


def test_verify_identity_token_bad_iss(apple_jwks_rs: rsa.RSAPrivateKey) -> None:
    token = _mint_token(apple_jwks_rs, iss="https://evil.example")
    with pytest.raises(AppleSignInError, match="issuer"):
        verify_identity_token(token)


def test_verify_identity_token_expired(apple_jwks_rs: rsa.RSAPrivateKey) -> None:
    token = _mint_token(apple_jwks_rs, exp_delta=-120)
    with pytest.raises(AppleSignInError, match="expired"):
        verify_identity_token(token)


def test_link_and_find_identity(pg_env: Path) -> None:
    linked = link_apple_identity(
        tenant_id="t1",
        user_id="u1",
        sub="sub-abc",
        email="u@privaterelay.appleid.com",
        is_private_relay=True,
        display_name="Ada",
    )
    assert linked["user_id"] == "u1"
    found = find_by_apple_sub("sub-abc")
    assert found is not None
    assert found["display_name"] == "Ada"
    token = get_or_create_app_account_token("t1", "u1")
    assert token == get_or_create_app_account_token("t1", "u1")


def test_link_refuses_different_user(pg_env: Path) -> None:
    link_apple_identity(tenant_id="t1", user_id="u1", sub="sub-x", email=None)
    with pytest.raises(AppleIdentityError, match="another account"):
        link_apple_identity(tenant_id="t1", user_id="u2", sub="sub-x", email=None)


def test_unlink_requires_other_login(pg_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    link_apple_identity(tenant_id="t1", user_id="u1", sub="sub-y", email=None)

    monkeypatch.setattr(
        "services.apple_identity_service.user_service.get_user_by_id",
        lambda _uid: {"id": "u1", "password": "", "passwordLoginEnabled": False},
    )
    with pytest.raises(AppleIdentityError, match="another login"):
        unlink_apple_identity(user_id="u1", sub="sub-y")

    monkeypatch.setattr(
        "services.apple_identity_service.user_service.get_user_by_id",
        lambda _uid: {"id": "u1", "password": "hash", "passwordLoginEnabled": True},
    )
    out = unlink_apple_identity(user_id="u1", sub="sub-y")
    assert out["unlinked_at"] is not None
    assert find_by_apple_sub("sub-y") is None


def test_link_required_conflict_path(apple_jwks_rs: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch) -> None:
    from modules import apple_auth_api

    token = _mint_token(apple_jwks_rs, email="taken@example.com")
    monkeypatch.setattr(apple_auth_api, "find_by_apple_sub", lambda _sub: None)
    monkeypatch.setattr(
        apple_auth_api.user_service,
        "get_user_by_email",
        lambda _email: {"id": "existing", "email": "taken@example.com", "status": "active"},
    )

    body = apple_auth_api.AppleSignInRequest(identity_token=token, email="taken@example.com")
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(apple_auth_api.mobile_apple_sign_in(body))
    assert excinfo.value.status_code == 409
    detail = excinfo.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "link_required"
    assert "email_hint" in detail


def test_existing_social_apple_account_logs_in(
    apple_jwks_rs: rsa.RSAPrivateKey, monkeypatch: pytest.MonkeyPatch
) -> None:
    from modules import apple_auth_api

    token = _mint_token(apple_jwks_rs, email="taken@example.com")
    social_user = {
        "id": "existing-apple",
        "email": "taken@example.com",
        "status": "active",
        "passwordLoginEnabled": False,
        "createdBy": "apple-sign-in",
        "tenantId": "t1",
    }
    monkeypatch.setattr(apple_auth_api, "find_by_apple_sub", lambda _sub: None)
    monkeypatch.setattr(apple_auth_api.user_service, "get_user_by_email", lambda _email: social_user)
    monkeypatch.setattr(apple_auth_api, "link_apple_identity", lambda **_kw: {"id": "aid"})
    monkeypatch.setattr(apple_auth_api, "maybe_store_refresh_from_authorization_code", lambda **_kw: None)
    monkeypatch.setattr(
        apple_auth_api,
        "_issue_with_app_account_token",
        lambda user: {"access_token": "access", "refresh_token": "refresh", "user": user},
    )

    body = apple_auth_api.AppleSignInRequest(identity_token=token, email="taken@example.com")
    result = asyncio.run(apple_auth_api.mobile_apple_sign_in(body))
    assert result["access_token"] == "access"
    assert result["user"]["id"] == "existing-apple"


def test_secrets_status_no_key_material(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services import apple_secrets

    missing = tmp_path / "missing.p8"
    monkeypatch.setenv("APPLE_SIGN_IN_PRIVATE_KEY_PATH", str(missing))
    monkeypatch.setenv("APPLE_IAP_PRIVATE_KEY_PATH", str(missing))
    status = apple_secrets.secrets_status()
    assert status["auth_key_exists"] is False
    assert status["iap_key_exists"] is False
    assert "BEGIN" not in json.dumps(status)
