"""Unit tests for shared IG/FB comment context builder helpers."""

from __future__ import annotations

from services.customer_reply_v2.comment_context_builder import _collect_fb_urls, _collect_ig_urls, _normalize_media_type
from services.customer_reply_v2.inbound_video_comment import fb_video_source, ig_video_source
from services.customer_reply_v2.media_context import media_context_to_dict
from services.customer_reply_v2.models import CommentMediaContext


def test_normalize_and_collect_instagram_carousel_bounds() -> None:
    assert _normalize_media_type("CAROUSEL_ALBUM") == "carousel"
    payload = {
        "media_type": "CAROUSEL_ALBUM",
        "children": {
            "data": [
                {"media_url": "https://cdninstagram.com/1.jpg"},
                {"media_url": "https://cdninstagram.com/2.jpg"},
                {"media_url": "https://cdninstagram.com/3.jpg"},
                {"media_url": "https://cdninstagram.com/4.jpg"},
            ]
        },
    }
    mtype, urls, truncated = _collect_ig_urls(payload)
    assert mtype == "carousel"
    assert len(urls) == 3
    assert truncated is True


def test_collect_instagram_reel_uses_thumbnail_only() -> None:
    mtype, urls, truncated = _collect_ig_urls(
        {
            "media_type": "REELS",
            "media_url": "https://cdninstagram.com/video.mp4",
            "thumbnail_url": "https://cdninstagram.com/thumb.jpg",
            "caption": "reel caption",
        }
    )
    assert mtype == "reel"
    assert urls == ["https://cdninstagram.com/thumb.jpg"]
    assert truncated is False


def test_collect_facebook_album_attachments() -> None:
    mtype, urls, truncated = _collect_fb_urls(
        {
            "message": "album post",
            "attachments": {
                "data": [
                    {
                        "type": "album",
                        "subattachments": {
                            "data": [
                                {"media": {"image": {"src": "https://scontent.xx.fbcdn.net/a.jpg"}}},
                                {"media": {"image": {"src": "https://scontent.xx.fbcdn.net/b.jpg"}}},
                            ]
                        },
                    }
                ]
            },
        }
    )
    assert mtype == "carousel"
    assert len(urls) == 2
    assert truncated is False


def test_media_context_dict_keeps_inputs_for_model_only() -> None:
    ctx = CommentMediaContext(
        media_type="image",
        caption="cap",
        media_status="available",
        saw_visuals=True,
        image_inputs=[{"url": "data:image/jpeg;base64,aaa", "kind": "image"}],
    )
    trace = media_context_to_dict(ctx, for_model=False)
    assert "image_inputs" not in trace
    assert trace["media_status"] == "available"
    model = media_context_to_dict(ctx, for_model=True)
    assert model["image_inputs"]


def test_facebook_video_source_is_file_not_thumbnail() -> None:
    post = {
        "message": "reel caption",
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
    assert fb_video_source(post) == "https://video.xx.fbcdn.net/clip.mp4"
    mtype, urls, _truncated = _collect_fb_urls(post)
    assert mtype == "video"
    assert urls[0] == "https://scontent.xx.fbcdn.net/thumb.jpg"


def test_instagram_reel_keeps_media_url_for_video_extract() -> None:
    payload = {
        "media_type": "REELS",
        "media_url": "https://cdninstagram.com/video.mp4",
        "thumbnail_url": "https://cdninstagram.com/thumb.jpg",
    }
    assert ig_video_source(payload) == "https://cdninstagram.com/video.mp4"
    _mtype, urls, _truncated = _collect_ig_urls(payload)
    assert urls == ["https://cdninstagram.com/thumb.jpg"]


def test_video_frames_reach_the_model() -> None:
    frames = [{"url": f"data:image/jpeg;base64,{index}", "kind": "video_frame"} for index in range(20)]
    ctx = CommentMediaContext(
        media_type="video",
        caption="cap",
        video_transcript="spoken line",
        image_inputs=[{"url": "data:image/jpeg;base64,thumb", "kind": "image"}, *frames],
        media_status="available",
        saw_visuals=True,
        frame_count=20,
    )
    model = media_context_to_dict(ctx, for_model=True)
    assert len(model["image_inputs"]) == 12
    assert model["image_inputs"][0]["url"].endswith("0")
    assert model["image_inputs"][-1]["url"].endswith("19")
    assert all(row["kind"] == "video_frame" for row in model["image_inputs"])
    assert model["video_transcript"] == "spoken line"
