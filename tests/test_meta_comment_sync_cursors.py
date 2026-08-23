"""Tests for Meta comment sync Postgres cursors."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from services.meta_comment_sync_cursors import (
    LEGACY_POSTS_CURSOR_KEY,
    POSTS_BACKFILL_CURSOR_KEY,
    extract_next_cursor,
    load_posts_backfill_cursor,
    save_posts_backfill_cursor,
)


def test_extract_next_cursor_returns_url_or_none() -> None:
    assert extract_next_cursor({"paging": {"next": "https://graph.facebook.com/page-2"}}) == (
        "https://graph.facebook.com/page-2"
    )
    assert extract_next_cursor({"paging": {}}) is None
    assert extract_next_cursor({}) is None


@patch("services.meta_comment_sync_cursors.postgres_enabled", return_value=True)
@patch("services.meta_comment_sync_cursors.load_sync_cursor")
def test_load_posts_backfill_cursor_prefers_backfill_key(load_sync: MagicMock, _pg: MagicMock) -> None:
    load_sync.side_effect = lambda *, binding_id, cursor_key: {
        POSTS_BACKFILL_CURSOR_KEY: "https://graph.facebook.com/backfill",
        LEGACY_POSTS_CURSOR_KEY: "https://graph.facebook.com/legacy",
    }.get(cursor_key)

    assert load_posts_backfill_cursor("bind_1") == "https://graph.facebook.com/backfill"
    assert load_sync.call_count == 1


@patch("services.meta_comment_sync_cursors.postgres_enabled", return_value=True)
@patch("services.meta_comment_sync_cursors.load_sync_cursor")
def test_load_posts_backfill_cursor_falls_back_to_legacy_posts(load_sync: MagicMock, _pg: MagicMock) -> None:
    load_sync.side_effect = lambda *, binding_id, cursor_key: {
        LEGACY_POSTS_CURSOR_KEY: "https://graph.facebook.com/legacy",
    }.get(cursor_key)

    assert load_posts_backfill_cursor("bind_1") == "https://graph.facebook.com/legacy"
    assert [call.kwargs["cursor_key"] for call in load_sync.call_args_list] == [
        POSTS_BACKFILL_CURSOR_KEY,
        LEGACY_POSTS_CURSOR_KEY,
    ]


@patch("services.meta_comment_sync_cursors.postgres_enabled", return_value=True)
@patch("services.meta_comment_sync_cursors.save_sync_cursor")
@patch("services.meta_comment_sync_cursors.load_sync_cursor", return_value="https://graph.facebook.com/legacy")
def test_save_posts_backfill_cursor_resets_empty_and_clears_legacy(
    load_sync: MagicMock,
    save_sync: MagicMock,
    _pg: MagicMock,
) -> None:
    save_posts_backfill_cursor("bind_1", None)

    assert save_sync.call_args_list[0].kwargs == {
        "binding_id": "bind_1",
        "cursor_key": POSTS_BACKFILL_CURSOR_KEY,
        "cursor_value": "",
        "expected_revision": None,
    }
    assert save_sync.call_args_list[1].kwargs == {
        "binding_id": "bind_1",
        "cursor_key": LEGACY_POSTS_CURSOR_KEY,
        "cursor_value": "",
        "expected_revision": None,
    }


@patch("services.meta_comment_sync_cursors.postgres_enabled", return_value=True)
@patch("services.meta_comment_sync_cursors.save_sync_cursor")
@patch("services.meta_comment_sync_cursors.load_sync_cursor", return_value=None)
def test_save_posts_backfill_cursor_persists_next_page(
    _load_sync: MagicMock,
    save_sync: MagicMock,
    _pg: MagicMock,
) -> None:
    save_posts_backfill_cursor("bind_1", "https://graph.facebook.com/page-3")

    assert save_sync.call_count == 1
    assert save_sync.call_args.kwargs["cursor_value"] == "https://graph.facebook.com/page-3"
    assert save_sync.call_args.kwargs["cursor_key"] == POSTS_BACKFILL_CURSOR_KEY
