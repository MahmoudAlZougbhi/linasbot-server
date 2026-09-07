"""Comment post watchlist: all posts by default, selected posts restrict AI."""

from __future__ import annotations

from services.comments_inbox.kinds import media_kind
from services.comments_inbox.watchlist import apply_watch_patch, comment_post_allowed, load_watchlist


def test_media_kind_reel_and_post() -> None:
    assert media_kind("REELS", platform="instagram") == "reel"
    assert media_kind("VIDEO", platform="instagram") == "reel"
    assert media_kind("IMAGE", platform="instagram") == "post"
    assert media_kind("video", platform="tiktok") == "video"
    assert media_kind("", platform="facebook") == "post"


def test_default_allows_every_post(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("services.comments_inbox.watchlist.get_data_root", lambda: str(tmp_path))
    assert comment_post_allowed("linas", "instagram", "1789") is True
    assert load_watchlist("linas")["instagram"]["mode"] == "all"


def test_selected_mode_blocks_other_posts(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("services.comments_inbox.watchlist.get_data_root", lambda: str(tmp_path))
    apply_watch_patch(
        "linas",
        platform="instagram",
        post_id="skip-me",
        selected=False,
        known_ids=["keep-me", "skip-me"],
    )
    assert comment_post_allowed("linas", "instagram", "keep-me") is True
    assert comment_post_allowed("linas", "instagram", "skip-me") is False
    assert comment_post_allowed("linas", "facebook", "skip-me") is True


def test_all_mode_clears_restriction(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("services.comments_inbox.watchlist.get_data_root", lambda: str(tmp_path))
    apply_watch_patch("linas", platform="tiktok", mode="selected", post_ids=["v1"])
    assert comment_post_allowed("linas", "tiktok", "v2") is False
    apply_watch_patch("linas", platform="tiktok", mode="all")
    assert comment_post_allowed("linas", "tiktok", "v2") is True
