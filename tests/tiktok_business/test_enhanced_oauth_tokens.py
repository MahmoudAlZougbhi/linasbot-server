"""K/J: advertiser vs account tokens, tenant isolation, OAuth state flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.tiktok_business.capabilities import TOKEN_KIND_ACCOUNT, TOKEN_KIND_ADVERTISER
from services.tiktok_business.errors import TikTokBusinessError, TikTokOAuthStateError
from services.tiktok_business.identity_api import identity_get
from services.tiktok_business.oauth_state import create_signed_state, parse_signed_state
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_enhanced import TikTokEnhancedRepository
from services.tiktok_business.token_guard import assert_advertiser_token
from tests.tiktok_business.conftest import seed_connection, seed_enhanced_binding


def test_account_state_stays_five_part_compatible(monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    signed = create_signed_state(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    parsed = parse_signed_state(signed.state)
    assert parsed["flow"] == "account"
    assert parsed["state"].count("|") if False else "|" not in parsed["nonce"]
    body = signed.state.rsplit(".", 1)[0]
    assert len(body.split("|")) == 5


def test_advertiser_state_is_six_part(monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    signed = create_signed_state(tenant_id="linas", actor_user_id="u1", return_surface="mobile", flow="advertiser")
    parsed = parse_signed_state(signed.state)
    assert parsed["flow"] == "advertiser"
    assert parsed["tenant_id"] == "linas"


def test_token_guard_blocks_account_holder_on_identity() -> None:
    with pytest.raises(TikTokBusinessError, match="account-holder"):
        assert_advertiser_token(path="/identity/get/", token_kind=TOKEN_KIND_ACCOUNT)
    with pytest.raises(TikTokBusinessError, match="account-holder"):
        assert_advertiser_token(path="/bc/asset/get/", token_kind=TOKEN_KIND_ACCOUNT)
    assert_advertiser_token(path="/identity/video/info/", token_kind=TOKEN_KIND_ADVERTISER)


@pytest.mark.asyncio
async def test_identity_get_never_calls_http_with_account_token(monkeypatch) -> None:
    called = {"n": 0}

    async def _req(**_k):
        called["n"] += 1
        return {}

    monkeypatch.setattr("services.tiktok_business.identity_api.tiktok_request", _req)
    with pytest.raises(TikTokBusinessError) as exc:
        await identity_get(access_token="account-token", token_kind=TOKEN_KIND_ACCOUNT, advertiser_id="1")
    assert exc.value.code == "token_type_mismatch"
    assert called["n"] == 0


def test_advertiser_credential_does_not_overwrite_account(tt_db) -> None:
    connection = seed_connection(tt_db)
    account_id = connection.credential_id
    seed_enhanced_binding(tt_db, connection, advertiser_token="ads-live", status="active", reason_code="ok")
    tt_db.refresh(connection)
    assert connection.credential_id == account_id
    opened = TikTokRepository(tt_db).open_tokens(connection)
    assert opened["access_token"] == "access-live"
    ads = TikTokEnhancedRepository(tt_db).open_advertiser_tokens(tenant_id="linas", connection_id=connection.id)
    assert ads is not None
    assert ads["access_token"] == "ads-live"
    assert ads["token_kind"] == TOKEN_KIND_ADVERTISER


def test_wrong_tenant_cannot_open_enhanced_binding(tt_db) -> None:
    connection = seed_connection(tt_db, tenant_id="linas")
    seed_enhanced_binding(tt_db, connection, advertiser_token="ads-live", advertiser_id="adv-1")
    other = TikTokEnhancedRepository(tt_db)
    assert other.get_binding(tenant_id="other", connection_id=connection.id) is None
    assert other.open_advertiser_tokens(tenant_id="other", connection_id=connection.id) is None


def test_ads_callback_module_never_reads_query_tenant() -> None:
    source = Path("modules/tiktok_ads_oauth.py").read_text(encoding="utf-8")
    assert 'params.get("tenant_id")' not in source
    assert "Never read tenant_id" in source


@pytest.mark.asyncio
async def test_account_oauth_rejects_advertiser_flow(monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    signed = create_signed_state(tenant_id="linas", actor_user_id="u1", return_surface="web", flow="advertiser")
    from services.tiktok_business.oauth import complete_tiktok_oauth

    with pytest.raises(TikTokOAuthStateError, match="ads callback"):
        await complete_tiktok_oauth(state=signed.state, code="x", error=None, error_description=None)


def test_store_advertiser_keeps_separate_token_kind(tt_db) -> None:
    from db.models.tiktok_business import TikTokCredential

    connection = seed_connection(tt_db)
    repo = TikTokEnhancedRepository(tt_db)
    cred = repo.store_advertiser_credential(
        connection=connection,
        access_token="adv",
        refresh_token="r",
        scopes=[],
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_expires_at=None,
    )
    stored = tt_db.get(TikTokCredential, cred.id)
    account = tt_db.get(TikTokCredential, connection.credential_id)
    assert stored is not None and stored.token_kind == TOKEN_KIND_ADVERTISER
    assert account is not None and account.token_kind == TOKEN_KIND_ACCOUNT
    assert connection.credential_id != cred.id


def test_ads_oauth_start_builds_marketing_url(tt_db) -> None:
    from services.tiktok_business.ads_oauth import start_tiktok_ads_oauth

    seed_connection(tt_db)
    started = start_tiktok_ads_oauth(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    assert started["success"] is True
    assert started["authorization_url"].startswith("https://ads.tiktok.com/marketing_api/auth?")
    assert "app_id=" in started["authorization_url"]
    from urllib.parse import parse_qs, urlparse

    state = parse_qs(urlparse(started["authorization_url"]).query)["state"][0]
    parsed = parse_signed_state(state)
    assert parsed["flow"] == "advertiser"
    assert parsed["tenant_id"] == "linas"


def test_ads_oauth_start_requires_connected_account(tt_db) -> None:
    from services.tiktok_business.ads_oauth import start_tiktok_ads_oauth

    with pytest.raises(TikTokBusinessError) as exc:
        start_tiktok_ads_oauth(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    assert exc.value.code == "TIKTOK_CONNECT_REQUIRED"


def test_dump_safe_redacts_marketing_secret() -> None:
    from services.tiktok_business.http_client import dump_safe

    dumped = dump_safe({"app_id": "1", "secret": "super-secret", "auth_code": "abc"})
    assert "super-secret" not in dumped
    assert "abc" not in dumped
    assert "[redacted]" in dumped
