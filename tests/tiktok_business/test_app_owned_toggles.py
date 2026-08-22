"""TikTok Messages/Comments switches are owner intent, not provider-scope gates."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.tiktok_business.status import tiktok_integration_row
from services.tiktok_business.toggles import set_tiktok_toggle
from tests.tiktok_business.conftest import seed_connection


def test_connected_account_stays_connected_without_comment_scopes(tt_db) -> None:
    seed_connection(
        tt_db,
        scopes=["user.info.basic", "video.list", "biz.spark.auth"],
        lifecycle="connected",
    )
    row = tiktok_integration_row("linas")
    assert row["connected"] is True
    assert row["connection_status"] == "connected"


@pytest.mark.asyncio
async def test_enable_comments_and_dm_without_provider_scopes(tt_db, monkeypatch) -> None:
    seed_connection(
        tt_db,
        scopes=["user.info.basic", "video.list", "biz.spark.auth"],
        lifecycle="connected",
    )
    monkeypatch.setattr("services.tiktok_business.toggles._set_action", lambda **_k: None)
    monkeypatch.setattr("services.tiktok_business.toggles._publish", AsyncMock())
    comments = await set_tiktok_toggle(tenant_id="linas", toggle="comments", enabled=True, actor="owner")
    dm = await set_tiktok_toggle(tenant_id="linas", toggle="dm", enabled=True, actor="owner")
    assert "toggles" in comments
    assert "toggles" in dm
