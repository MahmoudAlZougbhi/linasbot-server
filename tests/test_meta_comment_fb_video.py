"""Facebook comment video URL extraction and Brain analyze path."""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from services.brain.contracts.turn import HistorySnapshot
from services.integrations.meta.meta_comment_post_context import enrich_comment_event_post
from services.integrations.meta.meta_comment_post_context_fb_video import facebook_playable_video_url
from tests.test_meta_comment_replies import _binding


def test_facebook_playable_url_prefers_source_over_permalink() -> None:
    url = facebook_playable_video_url(
        {
            "type": "video",
            "source": "https://video.fbcdn.net/v/clip.mp4",
            "full_picture": "https://scontent.fbcdn.net/cover.jpg",
            "attachments": {
                "data": [
                    {
                        "type": "video_inline",
                        "url": "https://www.facebook.com/watch/?v=9",
                        "media": {"source": "https://video.fbcdn.net/v/clip.mp4"},
                    }
                ]
            },
        }
    )
    assert url == "https://video.fbcdn.net/v/clip.mp4"


def test_facebook_playable_url_ignores_watch_permalink() -> None:
    assert facebook_playable_video_url({"source": "https://www.facebook.com/watch/?v=1"}) == ""


@pytest.mark.asyncio
async def test_enrich_facebook_video_sets_video_url_not_cover_only() -> None:
    binding = _binding()

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/111_555"):
            return httpx.Response(
                200,
                json={
                    "id": "111_555",
                    "message": "Laser reel",
                    "type": "video",
                    "source": "https://video.fbcdn.net/v/laser.mp4",
                    "full_picture": "https://scontent.fbcdn.net/cover.jpg",
                },
            )
        raise AssertionError(path)

    event = {
        "channel": "facebook",
        "comment_id": "c-video",
        "post_id": "111_555",
        "text": "price?",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        out = await enrich_comment_event_post(
            event,
            binding=binding,
            token="token",
            graph_api_version="v24.0",
            client=client,
        )
    assert out["media_type"] == "VIDEO"
    assert out["video_url"] == "https://video.fbcdn.net/v/laser.mp4"
    assert "https://scontent.fbcdn.net/cover.jpg" in out["image_urls"]
    assert "facebook.com" not in out["video_url"]


@pytest.mark.asyncio
async def test_facebook_video_comment_analyze_receives_video_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    async def fake_analyze(**kwargs):
        captured.update(kwargs)
        return {
            "status": "ok",
            "transcript": "offer",
            "visual_description": "frames of laser",
            "duration_s": 8.0,
            "truncated": False,
            "frame_count": 4,
        }

    monkeypatch.setattr("services.brain.media.comment_attach.analyze_post_media", fake_analyze)
    monkeypatch.setattr("services.brain.runtime.winning_comment_mode", lambda **_k: (None, None))
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": True, "reason": "", "detail": {}})(),
    )
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr("services.brain.runtime.load_history_snapshot", AsyncMock(return_value=HistorySnapshot()))

    async def fake_run(turn, *, message, channel):
        captured["frame_count"] = turn.extra.get("post_media_frame_count")
        captured["visual"] = turn.extra.get("post_visual_description")
        from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult

        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="ok")],
            ),
        )

    monkeypatch.setattr("services.brain.runtime.run_dm_after_gates", fake_run)
    monkeypatch.setattr(
        "services.brain.comments.pipeline.apply_ai_comment_destinations",
        lambda result, _mode, **_k: result,
    )
    monkeypatch.setattr("services.brain.runtime.apply_message_billing", lambda _turn, result: result)

    from services.billing.entitlements_service import entitlements_store
    from services.brain.runtime import run_customer_ai_comment

    entitlements_store.set_plan(tenant_id="fb-video", plan_id="starter", status="active", source="admin")
    outcome = await run_customer_ai_comment(
        tenant_id="fb-video",
        comment_text="how much",
        comment_id="c9",
        post_id="111_555",
        provider_sender_id="user-9",
        channel="facebook_comment",
        media_type="VIDEO",
        video_url="https://video.fbcdn.net/v/laser.mp4",
        image_urls=["https://scontent.fbcdn.net/cover.jpg"],
        caption="Laser reel",
    )
    assert outcome.stop is False
    assert captured["video_url"] == "https://video.fbcdn.net/v/laser.mp4"
    assert captured["media_type"] == "VIDEO"
    assert int(captured["frame_count"] or 0) > 0
    assert captured["visual"]
