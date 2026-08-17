"""Shared SQLite fixtures for TikTok Business tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ.setdefault("META_CREDENTIAL_ENCRYPTION_KEY", "x" * 32)
os.environ.setdefault("TIKTOK_CLIENT_KEY", "tt-client-key")
os.environ.setdefault("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
os.environ.setdefault("TIKTOK_REDIRECT_URI", "https://www.linasaibot.com/oauth/tiktok/callback")

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.tiktok_business.repository import TikTokRepository  # noqa: E402


@pytest.fixture()
def tt_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'tt.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_CREDENTIAL_ENCRYPTION_KEY", "x" * 32)
    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "tt-client-key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    yield session
    session.close()
    reset_engine_for_tests()


def seed_connection(
    session,
    *,
    tenant_id: str = "linas",
    open_id: str = "oid-1",
    scopes: list[str] | None = None,
    access_token: str = "access-live",
    refresh_token: str = "refresh-live",
    lifecycle: str = "connected",
):
    repo = TikTokRepository(session)
    row = repo.upsert_connection(
        tenant_id=tenant_id,
        actor_user_id="owner-1",
        open_id=open_id,
        display_name="Linas TT",
        username="linas_tt",
        avatar_url="https://example.test/a.png",
        scopes=scopes
        or [
            "user.info.basic",
            "video.list",
            "comment.list",
            "comment.list.manage",
            "biz.spark.auth",
        ],
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=datetime.now(UTC) + timedelta(hours=12),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=30),
        lifecycle_status=lifecycle,
    )
    session.commit()
    return row
