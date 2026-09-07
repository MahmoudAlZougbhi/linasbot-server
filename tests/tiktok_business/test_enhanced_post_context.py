"""B/C/D/E/G: post-context resolver levels and official media handling."""

from __future__ import annotations

import pytest

from services.tiktok_business.post_context import context_level_for, resolve_tiktok_post_context
from tests.tiktok_business.conftest import seed_connection, seed_enhanced_binding


def _async_val(value):
    async def _inner(*_a, **_k):
        return value

    return _inner


@pytest.mark.asyncio
async def test_b_identity_without_media_url_is_caption_thumbnail(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    seed_enhanced_binding(
        tt_db,
        connection,
        status="limited",
        reason_code="ok",
        advertiser_token="ads",
        advertiser_id="adv-1",
        identity_id="id-1",
        identity_type="TT_USER",
        capabilities={"identity_video_query": True},
    )

    async def _live(**_k):
        return {
            "caption": "laser underarm",
            "thumbnail_url": "https://tiktokcdn.test/cover.jpg",
            "share_url": "",
            "video_url": "",
        }

    async def _info(**_k):
        return {"caption": "laser underarm", "thumbnail_url": "https://tiktokcdn.test/cover.jpg", "media_url": ""}

    async def _build(**kwargs):
        assert not kwargs.get("video_url")
        return {
            "caption": kwargs["caption"],
            "video_transcript": "",
            "frame_count": 0,
            "video_status": "",
            "tiktok_raw_video": False,
        }

    monkeypatch.setattr("services.tiktok_business.post_context.fetch_tiktok_video_item", _live)
    monkeypatch.setattr("services.tiktok_business.post_context.identity_video_info", _info)
    monkeypatch.setattr("services.tiktok_business.post_context.build_tiktok_comment_context", _build)
    monkeypatch.setattr("services.tiktok_business.post_context.ensure_fresh_advertiser_token", _async_val("ads"))
    out = await resolve_tiktok_post_context(
        tenant_id="linas",
        connection_id=connection.id,
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        account_token="acc",
        open_id="oid-1",
    )
    assert out["context_level"] == "caption_thumbnail"
    assert out["context_level"] != "full_video"
    assert "did not see" in out["comment_context"]["tiktok_context_note"]


@pytest.mark.asyncio
async def test_c_official_media_url_is_full_video(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    seed_enhanced_binding(
        tt_db,
        connection,
        status="active",
        reason_code="ok",
        advertiser_token="ads",
        advertiser_id="adv-1",
        identity_id="id-1",
        identity_type="TT_USER",
    )

    async def _live(**_k):
        return {"caption": "offer", "thumbnail_url": "https://tiktokcdn.test/c.jpg", "video_url": ""}

    async def _info(**_k):
        return {
            "caption": "offer",
            "thumbnail_url": "https://tiktokcdn.test/c.jpg",
            "media_url": "https://tiktokcdn.test/v.mp4",
        }

    async def _build(**kwargs):
        assert kwargs.get("video_url") == "https://tiktokcdn.test/v.mp4"
        return {
            "caption": "offer",
            "video_transcript": "hello from video",
            "frame_count": 4,
            "video_status": "extracted",
            "tiktok_raw_video": True,
        }

    monkeypatch.setattr("services.tiktok_business.post_context.fetch_tiktok_video_item", _live)
    monkeypatch.setattr("services.tiktok_business.post_context.identity_video_info", _info)
    monkeypatch.setattr("services.tiktok_business.post_context.build_tiktok_comment_context", _build)
    monkeypatch.setattr("services.tiktok_business.post_context.ensure_fresh_advertiser_token", _async_val("ads"))
    out = await resolve_tiktok_post_context(
        tenant_id="linas",
        connection_id=connection.id,
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        account_token="acc",
        open_id="oid-1",
    )
    assert out["context_level"] == "full_video"
    assert out["source_capabilities"]["full_video_context_available"] is True


@pytest.mark.asyncio
async def test_d_expired_media_url_refreshes_once(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    seed_enhanced_binding(
        tt_db,
        connection,
        status="active",
        reason_code="ok",
        advertiser_token="ads",
        advertiser_id="adv-1",
        identity_id="id-1",
        identity_type="TT_USER",
    )
    calls = {"info": 0, "build": 0}

    async def _live(**_k):
        return {"caption": "cap", "thumbnail_url": "https://tiktokcdn.test/c.jpg", "video_url": ""}

    async def _info(**_k):
        calls["info"] += 1
        if calls["info"] == 1:
            return {"media_url": "https://tiktokcdn.test/old.mp4", "caption": "cap", "thumbnail_url": ""}
        return {"media_url": "https://tiktokcdn.test/old.mp4", "caption": "cap", "thumbnail_url": ""}

    async def _build(**kwargs):
        calls["build"] += 1
        if kwargs.get("video_url"):
            return {
                "caption": "cap",
                "video_transcript": "",
                "frame_count": 0,
                "video_status": "http_403",
                "tiktok_raw_video": True,
            }
        return {
            "caption": "cap",
            "video_transcript": "",
            "frame_count": 0,
            "video_status": "",
            "tiktok_raw_video": False,
            "video_raw_unavailable": "tiktok_official_mp4_missing",
        }

    monkeypatch.setattr("services.tiktok_business.post_context.fetch_tiktok_video_item", _live)
    monkeypatch.setattr("services.tiktok_business.post_context.identity_video_info", _info)
    monkeypatch.setattr("services.tiktok_business.post_context.build_tiktok_comment_context", _build)
    monkeypatch.setattr("services.tiktok_business.post_context.ensure_fresh_advertiser_token", _async_val("ads"))
    out = await resolve_tiktok_post_context(
        tenant_id="linas",
        connection_id=connection.id,
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        account_token="acc",
        open_id="oid-1",
    )
    assert calls["info"] == 2
    assert out["diagnostics"]["media_refresh_attempted"] is True
    assert out["context_level"] != "full_video"
    assert out["comment_context"]["tiktok_raw_video"] is False


@pytest.mark.asyncio
async def test_e_audio_transcript_in_full_video_context(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)

    async def _live(**_k):
        return {"caption": "cap", "thumbnail_url": "", "video_url": "https://tiktokcdn.test/v.mp4"}

    async def _build(**kwargs):
        return {
            "caption": "cap",
            "video_transcript": "full spoken offer from the video",
            "frame_count": 2,
            "video_status": "extracted",
            "tiktok_raw_video": True,
        }

    monkeypatch.setattr("services.tiktok_business.post_context.fetch_tiktok_video_item", _live)
    monkeypatch.setattr("services.tiktok_business.post_context.build_tiktok_comment_context", _build)
    out = await resolve_tiktok_post_context(
        tenant_id="linas",
        connection_id=connection.id,
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        account_token="acc",
        open_id="oid-1",
    )
    assert out["context_level"] == "full_video"
    assert "full spoken offer" in out["comment_context"]["video_transcript"]


@pytest.mark.asyncio
async def test_g_what_is_this_receives_real_caption(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)

    async def _live(**_k):
        return {
            "caption": "underarm laser 3 sessions",
            "thumbnail_url": "https://tiktokcdn.test/c.jpg",
            "video_url": "",
        }

    async def _build(**kwargs):
        return {
            "caption": kwargs["caption"],
            "comment_text": kwargs["comment_text"],
            "video_transcript": "",
            "frame_count": 0,
            "video_status": "",
            "tiktok_raw_video": False,
        }

    monkeypatch.setattr("services.tiktok_business.post_context.fetch_tiktok_video_item", _live)
    monkeypatch.setattr("services.tiktok_business.post_context.build_tiktok_comment_context", _build)
    out = await resolve_tiktok_post_context(
        tenant_id="linas",
        connection_id=connection.id,
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        account_token="acc",
        open_id="oid-1",
    )
    assert out["caption"] == "underarm laser 3 sessions"
    assert out["comment_context"]["comment_text"] == "what is this"
    assert out["context_level"] == "caption_thumbnail"


def test_f_long_video_offsets_still_cover_full_duration() -> None:
    from services.customer_reply_v2.inbound_video import MAX_FRAMES, frame_offsets_s

    offsets = frame_offsets_s(20 * 60)
    assert len(offsets) == MAX_FRAMES
    assert offsets[0] == 0.0
    assert offsets[-1] >= 1100.0


@pytest.mark.asyncio
async def test_a_resolver_skips_identity_without_advertiser_binding(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db)
    hits: list[str] = []

    async def _live(**_k):
        return {"caption": "offer", "thumbnail_url": "https://tiktokcdn.test/c.jpg", "video_url": ""}

    async def _info(**_k):
        hits.append("identity")
        raise AssertionError("identity must not run")

    async def _build(**kwargs):
        return {
            "caption": kwargs["caption"],
            "video_transcript": "",
            "frame_count": 0,
            "video_status": "",
            "tiktok_raw_video": False,
        }

    monkeypatch.setattr("services.tiktok_business.post_context.fetch_tiktok_video_item", _live)
    monkeypatch.setattr("services.tiktok_business.post_context.identity_video_info", _info)
    monkeypatch.setattr("services.tiktok_business.post_context.build_tiktok_comment_context", _build)
    out = await resolve_tiktok_post_context(
        tenant_id="linas",
        connection_id=connection.id,
        comment_text="what is this",
        comment_id="c1",
        video_id="v1",
        account_token="acc",
        open_id="oid-1",
    )
    assert hits == []
    assert out["context_level"] == "caption_thumbnail"
    assert out["diagnostics"]["identity_used"] is False


def test_context_level_never_full_video_without_processed_media() -> None:
    assert context_level_for(caption="x", thumbnail_url="https://t", frame_count=0, transcript="", video_ok=False) == (
        "caption_thumbnail"
    )
    assert (
        context_level_for(caption="", thumbnail_url="", frame_count=0, transcript="", video_ok=False) == "comment_only"
    )
