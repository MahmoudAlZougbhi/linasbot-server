"""Read-only enhanced probe contract + Accounts scopes stay frozen."""

from __future__ import annotations

import pytest

from services.tiktok_business.config import REQUESTED_SCOPES
from services.tiktok_business.live_probe import probe_linas_enhanced_readonly
from tests.tiktok_business.conftest import seed_connection


def test_requested_scopes_unchanged() -> None:
    assert REQUESTED_SCOPES == (
        "user.info.basic",
        "video.list",
        "comment.list",
        "comment.list.manage",
        "biz.spark.auth",
    )
    joined = ",".join(REQUESTED_SCOPES)
    assert "identity" not in joined
    assert "bc." not in joined
    assert "advertiser" not in joined


@pytest.mark.asyncio
async def test_live_probe_classifies_without_identity_http(tt_db, monkeypatch) -> None:
    seed_connection(tt_db)
    called = {"n": 0}

    async def _req(**_k):
        called["n"] += 1
        return {}

    monkeypatch.setattr("services.tiktok_business.identity_api.tiktok_request", _req)
    out = await probe_linas_enhanced_readonly(tenant_id="linas")
    assert out["account_token_identity_guard"] == "token_type_mismatch"
    assert called["n"] == 0
    assert out["enhanced_video_context"]["status"] == "authorization_required"
    assert out["acceptable"] is True
