"""Facebook, Instagram, and TikTok comment vision: caption + frames + full audio."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.customer_reply_v2.comment_context_builder import build_production_comment_context
from services.tiktok_business.comment_context import build_tiktok_comment_context


def _binding(*, channel: str, auth_flow: str) -> SimpleNamespace:
    return SimpleNamespace(channel=channel, auth_flow=auth_flow, asset_id="asset-1")


async def _frames_and_transcript(**kwargs):
    assert str(kwargs.get("video_url") or "").startswith("https://")
    return {
        "image_inputs": [{"url": f"data:image/jpeg;base64,f{index}", "kind": "video_frame"} for index in range(8)],
        "video_status": "extracted",
        "transcript": "full spoken offer for underarm laser this week",
        "frame_count": 8,
    }


@pytest.mark.asyncio
async def test_facebook_comment_gets_caption_frames_and_full_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_graph(_client, *, url, token, params=None):
        _ = token, params
        if url.endswith("/comments") or "/comments" in url:
            return {"data": []}
        return {
            "message": "Summer laser offer",
            "permalink_url": "https://facebook.com/p",
            "attachments": {
                "data": [
                    {
                        "type": "video_inline",
                        "media": {
                            "image": {"src": "https://cdn.example/thumb.jpg"},
                            "source": "https://cdn.example/fb.mp4",
                        },
                    }
                ]
            },
        }

    async def fake_bytes(_client, url: str) -> str:
        _ = url
        return "data:image/jpeg;base64,thumb"

    monkeypatch.setattr(
        "services.customer_reply_v2.comment_context_builder._graph_get_json",
        fake_graph,
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.comment_context_builder._fetch_bytes_as_data_url",
        fake_bytes,
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.comment_context_builder.attach_comment_video_frames",
        _frames_and_transcript,
    )
    out = await build_production_comment_context(
        client=object(),
        binding=_binding(channel="facebook", auth_flow="facebook_login"),
        token="t",
        graph_api_version="v24.0",
        tenant_id="linas",
        comment_text="What is this",
        comment_id="c-fb",
        media_id="p-fb",
    )
    assert out["platform"] == "facebook"
    assert out["caption"] == "Summer laser offer"
    assert out["video_transcript"] == "full spoken offer for underarm laser this week"
    assert out["video_status"] == "extracted"
    assert len(out["image_inputs"]) == 8
    assert out["media_status"] == "available"


@pytest.mark.asyncio
async def test_instagram_comment_gets_caption_frames_and_full_audio(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_graph(_client, *, url, token, params=None):
        _ = token, params
        if url.endswith("/replies") or "/replies" in url:
            return {"data": []}
        if url.endswith("/c-ig"):
            return {"text": "What is this", "username": "tester"}
        return {
            "caption": "New underarm reel",
            "media_type": "REELS",
            "media_url": "https://cdn.example/ig.mp4",
            "thumbnail_url": "https://cdn.example/ig-thumb.jpg",
            "permalink": "https://instagram.com/p",
        }

    async def fake_bytes(_client, url: str) -> str:
        _ = url
        return "data:image/jpeg;base64,thumb"

    monkeypatch.setattr(
        "services.customer_reply_v2.comment_context_builder._graph_get_json",
        fake_graph,
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.comment_context_builder._fetch_bytes_as_data_url",
        fake_bytes,
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.comment_context_builder.attach_comment_video_frames",
        _frames_and_transcript,
    )
    out = await build_production_comment_context(
        client=object(),
        binding=_binding(channel="instagram", auth_flow="instagram_login"),
        token="t",
        graph_api_version="v26.0",
        tenant_id="linas",
        comment_text="What is this",
        comment_id="c-ig",
        media_id="m-ig",
    )
    assert out["platform"] == "instagram"
    assert out["caption"] == "New underarm reel"
    assert out["video_transcript"] == "full spoken offer for underarm laser this week"
    assert len(out["image_inputs"]) == 8
    assert out["media_status"] == "available"


@pytest.mark.asyncio
async def test_tiktok_comment_gets_caption_and_uses_video_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_fetch(url: str, *, max_bytes: int, timeout_s: float | None = None) -> dict:
        _ = max_bytes, timeout_s
        return {"ok": True, "bytes": b"jpeg-bytes", "mime": "image/jpeg", "url": url, "error": ""}

    monkeypatch.setattr("services.tiktok_business.comment_context.fetch_inbound_url", fake_fetch)
    monkeypatch.setattr(
        "services.tiktok_business.comment_context.attach_comment_video_frames",
        _frames_and_transcript,
    )
    out = await build_tiktok_comment_context(
        tenant_id="linas",
        comment_text="What is this",
        comment_id="c-tt",
        video_id="v-tt",
        caption="TikTok laser offer",
        thumbnail_url="https://cdn.example/tt.jpg",
        video_url="https://cdn.example/tt.mp4",
    )
    assert out["platform"] == "tiktok"
    assert out["caption"] == "TikTok laser offer"
    assert out["tiktok_raw_video"] is True
    assert out["video_transcript"] == "full spoken offer for underarm laser this week"
    assert len(out["image_inputs"]) == 8
    assert out["media_status"] == "available"
