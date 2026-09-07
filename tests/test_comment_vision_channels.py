"""Shared comment video extract: real file URLs plus frames and full transcript."""

from __future__ import annotations

import pytest

from services.customer_reply_v2.inbound_video_comment import (
    attach_comment_video_frames,
    fb_video_source,
    ig_video_source,
)


def test_facebook_and_instagram_keep_real_video_files() -> None:
    fb = {
        "message": "underarm laser",
        "attachments": {
            "data": [
                {
                    "type": "video_inline",
                    "media": {
                        "image": {"src": "https://scontent.xx.fbcdn.net/thumb.jpg"},
                        "source": "https://video.xx.fbcdn.net/clip.mp4",
                    },
                }
            ]
        },
    }
    ig = {
        "media_type": "REELS",
        "media_url": "https://cdninstagram.com/reel.mp4",
        "thumbnail_url": "https://cdninstagram.com/thumb.jpg",
        "caption": "underarm laser",
    }
    assert fb_video_source(fb) == "https://video.xx.fbcdn.net/clip.mp4"
    assert ig_video_source(ig) == "https://cdninstagram.com/reel.mp4"


@pytest.mark.asyncio
async def test_attach_sends_adaptive_frames_and_full_transcript(monkeypatch: pytest.MonkeyPatch) -> None:
    frames = [b"frame-one", b"frame-two", b"frame-three"]

    async def _fetch(url: str, *, max_bytes: int, timeout_s: float | None = None) -> dict:
        _ = max_bytes, timeout_s
        assert url.endswith(".mp4")
        return {"ok": True, "bytes": b"fake-mp4", "error": ""}

    def _extract(data: bytes) -> dict:
        assert data == b"fake-mp4"
        return {"status": "extracted", "frames": frames, "audio": b"wav", "duration_s": 12.0, "interval_s": 5.0}

    async def _stt(data: bytes) -> dict:
        assert data == b"wav"
        return {"ok": True, "text": "full spoken offer from start to end", "model": "whisper-1"}

    monkeypatch.setattr("services.customer_reply_v2.inbound_video_comment.fetch_inbound_url", _fetch)
    monkeypatch.setattr("services.customer_reply_v2.inbound_video_comment.extract_bounded_video", _extract)
    monkeypatch.setattr("services.customer_reply_v2.inbound_video_comment.transcribe_full_wav", _stt)
    monkeypatch.setattr("services.customer_reply_v2.inbound_video_comment.save_cached_media", lambda *_a, **_k: None)
    extra = await attach_comment_video_frames(
        tenant_id="linas",
        media_revision="rev",
        video_url="https://cdn.example.test/clip.mp4",
        image_inputs=[{"url": "data:image/jpeg;base64,thumb", "kind": "image"}],
    )
    assert extra["frame_count"] == 3
    assert extra["transcript"] == "full spoken offer from start to end"
    assert extra["image_inputs"][0]["kind"] == "image"
    assert extra["image_inputs"][1]["kind"] == "video_frame"
