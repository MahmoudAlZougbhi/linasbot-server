"""TikTok comment context sends caption + thumbnail; raw MP4 is optional."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.tiktok_business.comment_context import build_tiktok_comment_context, tiktok_video_source


def test_tiktok_video_source_only_https() -> None:
    row = SimpleNamespace(video_url="", download_url="https://example.com/v.mp4", media_url="")
    assert tiktok_video_source(row) == "https://example.com/v.mp4"
    assert tiktok_video_source(SimpleNamespace()) == ""


@pytest.mark.asyncio
async def test_tiktok_context_uses_caption_without_inventing_video(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fetch(url: str, *, max_bytes: int, timeout_s: float | None = None) -> dict:
        _ = url, max_bytes, timeout_s
        return {"ok": True, "bytes": b"jpeg-bytes", "mime": "image/jpeg", "url": url, "error": ""}

    monkeypatch.setattr("services.tiktok_business.comment_context.fetch_inbound_url", _fetch)
    out = await build_tiktok_comment_context(
        tenant_id="linas",
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        caption="laser underarm offer",
        thumbnail_url="https://tiktokcdn.com/cover.jpg",
    )
    assert out["caption"] == "laser underarm offer"
    assert out["platform"] == "tiktok"
    assert out["image_input_count"] == 1
    assert out["tiktok_raw_video"] is False
    assert out["video_raw_unavailable"] == "tiktok_video_list_has_no_mp4"
    assert out["video_transcript"] == ""
