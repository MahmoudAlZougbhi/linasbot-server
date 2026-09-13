"""One-shot post media analysis is cached and reused on later comments."""

from __future__ import annotations

import fakeredis
import pytest

from services.customer_ai.contracts.turn import CustomerTurn, MediaView
from services.customer_ai.media_analysis.analyze import analyze_post_media, is_video_media_type
from services.customer_ai.media_analysis.cache import (
    get_analysis,
    put_analysis,
    set_post_media_redis_for_tests,
)
from services.customer_ai.media_analysis.comment_attach import analysis_fields_for_comment
from services.customer_ai.turn_pipeline import inbound_task_text


def setup_function() -> None:
    set_post_media_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))


def teardown_function() -> None:
    set_post_media_redis_for_tests(None)


def test_video_media_type_detects_reels() -> None:
    assert is_video_media_type("VIDEO") is True
    assert is_video_media_type("REEL") is True
    assert is_video_media_type("IMAGE") is False


def test_cache_round_trip() -> None:
    payload = {"status": "ok", "transcript": "hello", "visual_description": "a clinic lobby"}
    assert put_analysis(tenant_id="linas", post_id="ig_1", payload=payload) is True
    got = get_analysis(tenant_id="linas", post_id="ig_1")
    assert got is not None
    assert got["transcript"] == "hello"
    assert get_analysis(tenant_id="linas", post_id="other") is None


@pytest.mark.asyncio
async def test_second_comment_reuses_cached_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    async def _run(**_kwargs: object) -> dict[str, object]:
        calls["n"] += 1
        return {
            "status": "ok",
            "transcript": "welcome to the clinic",
            "visual_description": "laser machine on screen",
            "duration_s": 42.0,
            "analyze_duration_s": 42.0,
            "frame_count": 9,
            "interval_s": 5.0,
            "truncated": False,
            "kind": "video",
        }

    monkeypatch.setattr("services.customer_ai.media_analysis.analyze._run", _run)
    first = await analyze_post_media(
        tenant_id="linas",
        post_id="reel-9",
        media_type="VIDEO",
        urls=["https://cdn.example/reel.mp4"],
    )
    second = await analyze_post_media(
        tenant_id="linas",
        post_id="reel-9",
        media_type="VIDEO",
        urls=["https://cdn.example/reel.mp4"],
    )
    assert calls["n"] == 1
    assert first.get("cache_hit") is not True
    assert second["cache_hit"] is True
    assert second["transcript"] == "welcome to the clinic"


@pytest.mark.asyncio
async def test_comment_fields_include_caption_ready_analysis(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _analyze(**_kwargs: object) -> dict[str, object]:
        return {
            "status": "ok",
            "transcript": "prices this week",
            "visual_description": "price list card",
            "duration_s": 12,
            "truncated": False,
            "frame_count": 3,
            "cache_hit": True,
        }

    monkeypatch.setattr("services.customer_ai.media_analysis.comment_attach.analyze_post_media", _analyze)
    fields = await analysis_fields_for_comment(
        tenant_id="linas",
        post_id="img-2",
        media_type="IMAGE",
        urls=["https://cdn.example/post.jpg"],
        caption="Spring offer",
    )
    assert fields["post_transcript"] == "prices this week"
    assert fields["post_visual_description"] == "price list card"
    assert fields["post_media_cache_hit"] is True


def test_inbound_task_text_sends_saved_analysis_with_comment() -> None:
    turn = CustomerTurn(
        tenant_id="t1",
        surface="comment",
        invocation_kind="comment",
        extra={
            "post_caption": "Spring laser reel",
            "post_media_type": "VIDEO",
            "post_transcript": "ask us for prices",
            "post_visual_description": "before after laser arms",
            "post_image_urls": ["https://cdn.example/reel.jpg"],
        },
    )
    blob = inbound_task_text(turn, "شو السعر؟")
    assert "Spring laser reel" in blob
    assert "post_audio_transcript=ask us for prices" in blob
    assert "post_visual=before after laser arms" in blob
    assert "https://cdn.example/reel.jpg" not in blob


def test_analyzed_inbound_image_does_not_use_visual_disabled_gate() -> None:
    from services.customer_ai.turn_pipeline import inbound_task_text as _task

    turn = CustomerTurn(
        tenant_id="lab",
        conversation_id="c1",
        event_ids=["m1"],
        media=MediaView(image_media_id="img-1", extract_preview="a white cream jar on a table"),
        extra={"response_language": "ar"},
    )
    assert "a white cream jar on a table" in _task(turn, "what is this?")
