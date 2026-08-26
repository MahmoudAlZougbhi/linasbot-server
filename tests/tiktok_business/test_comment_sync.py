"""TikTok comment poll: newest-first, skip owner comments, persist cursor when paged out."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from services.tiktok_business.comment_sync import persist_comment_page_cursor, should_enqueue_comment_ai
from services.tiktok_business.repository_content import TikTokContentRepository
from tests.tiktok_business.conftest import seed_connection


def test_should_enqueue_visitor_comment_after_connect() -> None:
    connected = datetime(2026, 8, 24, 16, 34, tzinfo=UTC)
    payload = {"owner": False, "comment_id": "c1"}
    assert (
        should_enqueue_comment_ai(
            created=True,
            is_reply=False,
            payload=payload,
            create_time=connected + timedelta(minutes=2),
            connected_at=connected,
        )
        is True
    )


def test_should_not_enqueue_owner_or_old_or_reply() -> None:
    connected = datetime(2026, 8, 24, 16, 34, tzinfo=UTC)
    after = connected + timedelta(minutes=2)
    before = connected - timedelta(minutes=2)
    assert (
        should_enqueue_comment_ai(
            created=True,
            is_reply=False,
            payload={"owner": True},
            create_time=after,
            connected_at=connected,
        )
        is False
    )
    assert (
        should_enqueue_comment_ai(
            created=True,
            is_reply=False,
            payload={"owner": False},
            create_time=before,
            connected_at=connected,
        )
        is False
    )
    assert (
        should_enqueue_comment_ai(
            created=True,
            is_reply=True,
            payload={"owner": False},
            create_time=after,
            connected_at=connected,
        )
        is False
    )
    assert (
        should_enqueue_comment_ai(
            created=False,
            is_reply=False,
            payload={"owner": False},
            create_time=after,
            connected_at=connected,
        )
        is False
    )
    assert (
        should_enqueue_comment_ai(
            created=True,
            is_reply=False,
            payload={"owner": False},
            create_time=None,
            connected_at=connected,
        )
        is False
    )


def test_upsert_reads_top_level_tiktok_comment_identity(tt_db) -> None:
    connection = seed_connection(tt_db)
    content = TikTokContentRepository(tt_db)
    media = content.upsert_media(tenant_id="linas", connection_id=connection.id, item_id="v1")
    row, created = content.upsert_comment(
        tenant_id="linas",
        connection_id=connection.id,
        media=media,
        payload={
            "comment_id": "c-top",
            "unique_identifier": "uid-visitor",
            "user_id": "legacy-id",
            "username": "visitor_tt",
            "display_name": "Visitor",
            "profile_image": "https://example.test/p.png",
            "text": "price?",
            "owner": False,
            "create_time": "1787591030",
        },
    )
    tt_db.commit()
    assert created is True
    assert row.author_user_id == "uid-visitor"
    assert row.author_username == "visitor_tt"
    assert row.is_reply is False


def test_comment_page_cursor_is_retained_when_limit_hit() -> None:
    stored, truncated = persist_comment_page_cursor(page_number=3, page_limit=3, has_more=True, cursor="keep-me")
    assert truncated is True
    assert stored == "keep-me"
