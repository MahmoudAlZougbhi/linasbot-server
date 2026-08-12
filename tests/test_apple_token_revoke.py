"""Tests for Apple token revoke + delete outbox (AuthKey only; never log PEM)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import create_engine, event, select

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.models.apple_billing import AuthExternalIdentityRow  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services import apple_token_revoke as revoke_mod  # noqa: E402
from services.apple_identity_service import link_apple_identity  # noqa: E402
from services.apple_revoke_outbox import (  # noqa: E402
    META_PENDING,
    META_REFRESH,
    enqueue_revoke,
    process_pending_revokes,
    revoke_on_account_delete,
)
from services.apple_token_revoke import (  # noqa: E402
    AppleTokenRevokeError,
    build_client_secret,
    exchange_authorization_code,
    revoke_apple_token,
)


@pytest.fixture()
def auth_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    private_key = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives import serialization

    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "AuthKey_TESTKEY1.p8"
    path.write_bytes(pem)
    monkeypatch.setenv("APPLE_SIGN_IN_PRIVATE_KEY_PATH", str(path))
    monkeypatch.setenv("APPLE_SIGN_IN_KEY_ID", "TESTKEY1")
    monkeypatch.setenv("APPLE_TEAM_ID", "TEAMTEST1")
    monkeypatch.setenv("APPLE_BUNDLE_ID", "com.linasai.app")
    # Ensure IAP path is distinct so tests can assert AuthKey usage.
    iap = tmp_path / "SubscriptionKey_IAPKEY.p8"
    iap.write_bytes(pem)
    monkeypatch.setenv("APPLE_IAP_PRIVATE_KEY_PATH", str(iap))
    return path


@pytest.fixture()
def pg_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'apple_revoke.db'}"
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


def test_build_client_secret_uses_auth_key_path(auth_key: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    real_read = revoke_mod.read_private_key_pem

    def _track(path: str) -> str:
        seen.append(path)
        return real_read(path)

    monkeypatch.setattr(revoke_mod, "read_private_key_pem", _track)
    token = build_client_secret()
    assert seen == [str(auth_key.resolve())]
    assert "SubscriptionKey" not in "".join(seen)
    header = jwt.get_unverified_header(token)
    assert header.get("alg") == "ES256"
    assert header.get("kid") == "TESTKEY1"
    claims = jwt.decode(token, options={"verify_signature": False})
    assert claims["iss"] == "TEAMTEST1"
    assert claims["sub"] == "com.linasai.app"
    assert claims["aud"] == "https://appleid.apple.com"
    # Never embed PEM in the JWT string itself beyond normal key material encoding —
    # assert we did not accidentally stringify the file path into logs via return.
    assert "BEGIN PRIVATE KEY" not in token


def test_exchange_and_revoke_mock_urllib(auth_key: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, dict[str, str]]] = []

    class _Resp:
        def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
            self.status = status
            self._raw = json.dumps(payload).encode("utf-8")

        def read(self) -> bytes:
            return self._raw

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    def _urlopen(req: Any, timeout: float = 0) -> _Resp:  # noqa: ARG001
        url = str(req.full_url)
        body = req.data.decode("utf-8") if req.data else ""
        import urllib.parse

        fields = dict(urllib.parse.parse_qsl(body))
        # Never assert full secrets; ensure form keys exist.
        assert "client_secret" in fields
        assert "client_id" in fields
        calls.append((url, {k: v for k, v in fields.items() if k != "client_secret" and k != "token" and k != "code"}))
        if url.endswith("/auth/token"):
            assert fields.get("grant_type") == "authorization_code"
            assert fields.get("code") == "auth-code-1"
            return _Resp(
                {
                    "access_token": "access-xyz",
                    "refresh_token": "refresh-xyz",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                }
            )
        if url.endswith("/auth/revoke"):
            assert fields.get("token_type_hint") == "refresh_token"
            assert fields.get("token") == "refresh-xyz"
            return _Resp({})
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(revoke_mod.urllib.request, "urlopen", _urlopen)

    tokens = exchange_authorization_code("auth-code-1")
    assert tokens["refresh_token"] == "refresh-xyz"
    out = revoke_apple_token(tokens["refresh_token"], "refresh_token")
    assert out.get("ok") is True or out == {}
    assert any(u.endswith("/auth/token") for u, _ in calls)
    assert any(u.endswith("/auth/revoke") for u, _ in calls)


def test_revoke_on_delete_enqueues_when_http_fails(
    auth_key: Path,
    pg_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link_apple_identity(tenant_id="t1", user_id="u-del", sub="sub-del", email="a@example.com")

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise AppleTokenRevokeError("Apple HTTP 500")

    monkeypatch.setattr("services.apple_revoke_outbox.exchange_authorization_code", _boom)
    monkeypatch.setattr("services.apple_revoke_outbox.revoke_apple_token", _boom)

    # Store refresh then delete-path revoke
    enqueue_revoke("u-del", "refresh-stored", "refresh_token")
    result = revoke_on_account_delete(user_id="u-del", authorization_code=None)
    assert result["enqueued"] is True
    assert result["revoked"] is False

    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(
                AuthExternalIdentityRow.user_id == "u-del",
            )
        ).scalar_one()
        meta = dict(row.meta or {})
        assert meta.get(META_REFRESH) == "refresh-stored"
        assert meta.get(META_PENDING)


def test_process_pending_revokes_success(
    auth_key: Path,
    pg_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    link_apple_identity(tenant_id="t1", user_id="u2", sub="sub-2", email=None)
    enqueue_revoke("u2", "refresh-pending", "refresh_token")

    monkeypatch.setattr(
        "services.apple_revoke_outbox.revoke_apple_token",
        lambda token, hint="refresh_token": {"ok": True},
    )
    out = process_pending_revokes(limit=10)
    assert out["succeeded"] >= 1
    with whatsapp_session() as session:
        row = session.execute(
            select(AuthExternalIdentityRow).where(AuthExternalIdentityRow.user_id == "u2")
        ).scalar_one()
        meta = dict(row.meta or {})
        assert META_PENDING not in meta
        assert META_REFRESH not in meta


def test_mobile_account_delete_calls_revoke(
    auth_key: Path,
    pg_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from modules import apple_auth_api

    link_apple_identity(tenant_id="t1", user_id="u-api", sub="sub-api", email=None)
    enqueue_revoke("u-api", "refresh-api", "refresh_token")

    called: dict[str, Any] = {}

    def _rev(*, user_id: str, authorization_code: str | None = None) -> dict[str, Any]:
        called["user_id"] = user_id
        called["authorization_code"] = authorization_code
        return {"enqueued": True, "revoked": True, "reason": "ok"}

    monkeypatch.setattr(apple_auth_api, "revoke_on_account_delete", _rev)
    monkeypatch.setattr(apple_auth_api, "unlink_all_apple_for_user", lambda _uid: 1)
    monkeypatch.setattr(
        apple_auth_api.mobile_refresh_token_service,
        "revoke_all_for_user",
        lambda _uid: None,
    )
    monkeypatch.setattr(apple_auth_api.session_service, "revoke_all_for_user", lambda _uid: None)
    monkeypatch.setattr(
        apple_auth_api.user_service,
        "mark_self_service_deleted",
        lambda _uid: {"id": "u-api", "status": "deleted"},
    )

    session = MagicMock()
    session.user_id = "u-api"
    session.tenant_id = "t1"
    monkeypatch.setattr(apple_auth_api, "require_session", lambda _req: session)

    async def _json() -> dict[str, Any]:
        return {"authorization_code": "code-from-client"}

    req = MagicMock()
    req.json = _json
    out = asyncio.run(apple_auth_api.mobile_account_delete(req))
    assert out["deleted"] is True
    assert called["user_id"] == "u-api"
    assert called["authorization_code"] == "code-from-client"


def test_client_secret_never_prints_pem(auth_key: Path, capsys: pytest.CaptureFixture[str]) -> None:
    secret = build_client_secret()
    captured = capsys.readouterr()
    combined = captured.out + captured.err + secret
    assert "BEGIN PRIVATE KEY" not in combined
    assert "BEGIN EC PRIVATE KEY" not in combined
