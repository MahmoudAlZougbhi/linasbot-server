"""Official TikTok video.list harvests an MP4 when present and stays honest when not."""

from __future__ import annotations

import pytest

from services.tiktok_business.video_source import (
    fetch_tiktok_video_item,
    parse_tiktok_video_item,
    pick_tiktok_video_url,
)


def test_pick_ignores_cover_and_keeps_official_mp4() -> None:
    row = {
        "item_id": "v1",
        "caption": "offer",
        "thumbnail_url": "https://tiktokcdn.com/cover.jpg",
        "share_url": "https://www.tiktok.com/@x/video/1",
        "video_info": {"url": "https://v16-webapp.tiktok.com/video/tos/clip.mp4"},
    }
    assert pick_tiktok_video_url(row) == "https://v16-webapp.tiktok.com/video/tos/clip.mp4"
    parsed = parse_tiktok_video_item(
        {"item_id": "v1", "caption": "offer", "thumbnail_url": "https://tiktokcdn.com/cover.jpg"}
    )
    assert parsed["video_url"] == ""
    assert parsed["caption"] == "offer"


@pytest.mark.asyncio
async def test_fetch_uses_video_ids_filter_then_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    async def _req(*, method: str, path: str, access_token: str, params: dict) -> dict:
        _ = method, path, access_token
        calls.append(params)
        if "filters" in params:
            return {"videos": []}
        return {
            "videos": [
                {
                    "item_id": "wanted",
                    "caption": "live caption",
                    "thumbnail_url": "https://tiktokcdn.com/cover.jpg",
                    "video_url": "https://example.com/file.mp4",
                }
            ]
        }

    monkeypatch.setattr("services.tiktok_business.video_source.tiktok_request", _req)
    out = await fetch_tiktok_video_item(access_token="tok", open_id="biz", video_id="wanted")
    assert out["caption"] == "live caption"
    assert out["video_url"] == "https://example.com/file.mp4"
    assert "filters" in calls[0]
    assert len(calls) == 2
