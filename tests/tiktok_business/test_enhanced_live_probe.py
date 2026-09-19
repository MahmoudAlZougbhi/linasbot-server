"""Accounts scopes stay frozen after the diagnostic live_probe helper was removed."""

from __future__ import annotations

from services.integrations.tiktok.config import REQUESTED_SCOPES


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
