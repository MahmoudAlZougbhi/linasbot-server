"""Token seal/open, missing scopes, tenant isolation, disconnect does not touch Meta."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.meta_app_registry import MetaCredentialError
from services.tiktok_business.crypto import open_tiktok_tokens, seal_tiktok_tokens
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.scopes import comments_manage_ready, messaging_send_ready
from services.tiktok_business.status import tiktok_integration_row
from tests.tiktok_business.conftest import seed_connection


def test_tokens_encrypted_roundtrip(tt_db) -> None:
    sealed = seal_tiktok_tokens(
        access_token="secret-access",
        refresh_token="secret-refresh",
        tenant_id="linas",
        connection_id="conn-1",
        scopes=["comment.list"],
    )
    assert "secret-access" not in sealed
    opened = open_tiktok_tokens(ciphertext=sealed, tenant_id="linas", connection_id="conn-1")
    assert opened["access_token"] == "secret-access"
    with pytest.raises(MetaCredentialError):
        open_tiktok_tokens(ciphertext=sealed, tenant_id="other", connection_id="conn-1")


def test_empty_token_refused() -> None:
    with pytest.raises(MetaCredentialError):
        seal_tiktok_tokens(
            access_token="  ",
            refresh_token="",
            tenant_id="linas",
            connection_id="c",
            scopes=[],
        )


def test_missing_comment_scopes_permission_required(tt_db) -> None:
    seed_connection(
        tt_db,
        scopes=["user.info.basic", "video.list", "biz.spark.auth"],
        lifecycle="permission_required",
    )
    row = tiktok_integration_row("linas")
    assert row["coming_soon"] is False
    assert row["connected"] is False
    assert row["connection_status"] == "permission_required"
    assert row["comments_state"]["blocker_code"] == "missing_comment_permissions"
    assert row["dm_state"]["blocker_code"] == "tiktok_messaging_pending"
    assert comments_manage_ready(row["granted_scopes"]) is False
    assert messaging_send_ready(row["granted_scopes"]) is False


def test_open_id_owned_by_other_tenant(tt_db) -> None:
    seed_connection(tt_db, tenant_id="tenant-a", open_id="shared-oid")
    repo = TikTokRepository(tt_db)
    with pytest.raises(PermissionError, match="other_tenant"):
        repo.upsert_connection(
            tenant_id="tenant-b",
            actor_user_id="u2",
            open_id="shared-oid",
            display_name="B",
            username="b",
            avatar_url="",
            scopes=["user.info.basic"],
            access_token="t-b",
            refresh_token="r-b",
            access_expires_at=datetime.now(UTC) + timedelta(hours=1),
            refresh_expires_at=None,
            lifecycle_status="connected",
        )


def test_sync_lease_exclusive(tt_db) -> None:
    connection = seed_connection(tt_db)
    repo = TikTokRepository(tt_db)
    first = repo.claim_sync_lease(connection.id, owner="node-a")
    assert first is not None
    second = repo.claim_sync_lease(connection.id, owner="node-b")
    assert second is None


def test_disconnect_revokes_only_tiktok(tt_db, monkeypatch) -> None:
    seed_connection(tt_db)
    called = {"meta": 0}

    async def _boom(*_a, **_k):
        called["meta"] += 1
        raise AssertionError("Meta disconnect must not run")

    monkeypatch.setattr("services.meta_connection_disconnect.disconnect_meta_binding_set", _boom)
    repo = TikTokRepository(tt_db)
    connection = repo.get_active_for_tenant("linas")
    assert connection is not None
    repo.mark_revoked(connection, actor="u1", reason="user_disconnect")
    tt_db.commit()
    assert repo.get_active_for_tenant("linas") is None
    assert called["meta"] == 0


@pytest.mark.asyncio
async def test_token_refresh_replaces_ciphertext(tt_db, monkeypatch) -> None:
    from db.models.tiktok_business import TikTokCredential
    from services.tiktok_business.oauth import ensure_fresh_token

    connection = seed_connection(tt_db, access_token="old-access", refresh_token="old-refresh")
    cred = tt_db.get(TikTokCredential, connection.credential_id)
    assert cred is not None
    cred.access_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    tt_db.commit()

    async def _refresh(*, refresh_token: str):
        assert refresh_token == "old-refresh"
        return {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 86400,
            "scope": "user.info.basic,video.list,comment.list,comment.list.manage,biz.spark.auth",
        }

    monkeypatch.setattr("services.tiktok_business.oauth.refresh_access_token", _refresh)
    repo = TikTokRepository(tt_db)
    token = await ensure_fresh_token(repo, connection)
    assert token == "new-access"
    opened = repo.open_tokens(connection)
    assert opened["access_token"] == "new-access"
    assert opened["refresh_token"] == "new-refresh"
    old = tt_db.get(TikTokCredential, cred.id)
    assert old is not None
    assert old.revoked_at is not None


def test_http_client_refuses_unsafe_paths() -> None:
    from services.tiktok_business.errors import TikTokApiError
    from services.tiktok_business.http_client import _safe_url

    with pytest.raises(TikTokApiError, match="unsafe"):
        _safe_url("https://evil.example/open_api/v1.3/business/get/")
    with pytest.raises(TikTokApiError, match="unsafe"):
        _safe_url("/../../etc/passwd")
    url = _safe_url("/business/comment/list/")
    assert url.startswith("https://business-api.tiktok.com/")
    assert "comment/list" in url
