"""OAuth state: tamper, replay, expiry, cross-tenant. Tenant never from query."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.tiktok_business.errors import TikTokOAuthStateError
from services.tiktok_business.oauth_state import create_signed_state, parse_signed_state
from services.tiktok_business.repository import TikTokRepository


def test_signed_state_roundtrip(tt_db, monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    signed = create_signed_state(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    parsed = parse_signed_state(signed.state)
    assert parsed["tenant_id"] == "linas"
    assert parsed["actor_user_id"] == "u1"
    assert parsed["return_surface"] == "mobile"
    assert parsed["state_hash"] == signed.state_hash


def test_state_tampering_rejected(monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    signed = create_signed_state(tenant_id="linas", actor_user_id="u1", return_surface="web")
    body, sig = signed.state.rsplit(".", 1)
    nonce, tenant, actor, surface, exp = body.split("|")
    tampered = f"{nonce}|other-tenant|{actor}|{surface}|{exp}.{sig}"
    with pytest.raises(TikTokOAuthStateError, match="signature"):
        parse_signed_state(tampered)


def test_state_expiry_rejected(monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    signed = create_signed_state(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    body, sig = signed.state.rsplit(".", 1)
    nonce, tenant, actor, surface, _exp = body.split("|")
    from services.tiktok_business.oauth_state import _sign

    expired_body = f"{nonce}|{tenant}|{actor}|{surface}|{int(time.time()) - 10}"
    expired_state = f"{expired_body}.{_sign(expired_body)}"
    with pytest.raises(TikTokOAuthStateError, match="expired"):
        parse_signed_state(expired_state)


def test_oauth_consume_replay_and_cross_tenant(tt_db) -> None:
    repo = TikTokRepository(tt_db)
    signed = create_signed_state(tenant_id="tenant-a", actor_user_id="u1", return_surface="mobile")
    repo.create_attempt(
        tenant_id="tenant-a",
        actor_user_id="u1",
        return_surface="mobile",
        state_hash=signed.state_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    tt_db.commit()
    first = repo.consume_attempt(state_hash=signed.state_hash, signed_tenant_id="tenant-a")
    assert first.status == "consumed"
    tt_db.commit()
    with pytest.raises(TikTokOAuthStateError, match="already used"):
        repo.consume_attempt(state_hash=signed.state_hash, signed_tenant_id="tenant-a")
    with pytest.raises(TikTokOAuthStateError, match="tenant mismatch|already used|unknown"):
        repo.consume_attempt(state_hash=signed.state_hash, signed_tenant_id="tenant-b")


def test_oauth_callback_module_never_reads_query_tenant() -> None:
    source = Path("modules/tiktok_business_oauth.py").read_text(encoding="utf-8")
    assert "params.get(\"tenant_id\")" not in source
    assert "query_params.get(\"tenant_id\")" not in source
    assert "Never read tenant_id" in source


def test_two_node_oauth_consume(tt_db) -> None:
    """HA nodes share Postgres CAS: only one consume succeeds (replay is the second node)."""

    repo = TikTokRepository(tt_db)
    signed = create_signed_state(tenant_id="tenant-a", actor_user_id="u1", return_surface="web")
    repo.create_attempt(
        tenant_id="tenant-a",
        actor_user_id="u1",
        return_surface="web",
        state_hash=signed.state_hash,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    tt_db.commit()
    won = repo.consume_attempt(state_hash=signed.state_hash, signed_tenant_id="tenant-a")
    tt_db.commit()
    assert won.status == "consumed"
    with pytest.raises(TikTokOAuthStateError, match="already used"):
        TikTokRepository(tt_db).consume_attempt(state_hash=signed.state_hash, signed_tenant_id="tenant-a")
