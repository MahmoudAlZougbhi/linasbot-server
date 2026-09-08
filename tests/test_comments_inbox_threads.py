"""Live Chat comment threads show customer comments even without an AI reply."""

from __future__ import annotations

from services.comments_inbox.thread_pairs import pair_comment_threads, pair_tiktok_threads
from services.meta_graph_routing import graph_api_version_for_binding
from services.meta_instagram_login_config import INSTAGRAM_LOGIN_GRAPH_API_VERSION


def test_instagram_comments_appear_without_ai_reply() -> None:
    threads = pair_comment_threads(
        [
            {"id": "c1", "text": "What is this", "username": "guest", "timestamp": "2026-09-08"},
            {"id": "c2", "text": "Nice", "username": "guest2"},
        ],
        platform="instagram",
        media_id="media1",
        names={"linaslaser"},
        ids={"1784"},
        limit=50,
    )
    assert [row["comment"] for row in threads] == ["What is this", "Nice"]
    assert threads[0]["ai_reply"] == ""
    assert threads[0]["delivery_status"] == "none"


def test_nested_and_parent_id_self_replies_attach() -> None:
    threads = pair_comment_threads(
        [
            {
                "id": "c1",
                "text": "Price?",
                "username": "guest",
                "replies": {"data": [{"id": "r1", "text": "DM us", "username": "linaslaser"}]},
            },
            {"id": "c2", "text": "Hours?", "username": "guest2"},
            {"id": "r2", "text": "10 to 6", "username": "linaslaser", "parent_id": "c2"},
            {"id": "r3", "text": "our own note", "username": "linaslaser"},
        ],
        platform="instagram",
        media_id="media1",
        names={"linaslaser"},
        ids=set(),
        limit=50,
    )
    by_comment = {row["comment"]: row["ai_reply"] for row in threads}
    assert by_comment == {"Price?": "DM us", "Hours?": "10 to 6"}


def test_facebook_self_reply_uses_from_id() -> None:
    threads = pair_comment_threads(
        [
            {
                "id": "c1",
                "message": "Hello",
                "from": {"name": "Sara", "id": "9"},
                "comments": {"data": [{"id": "r1", "message": "Hi Sara", "from": {"id": "page1"}}]},
            }
        ],
        platform="facebook",
        media_id="post1",
        names=set(),
        ids={"page1"},
        limit=10,
    )
    assert threads == [
        {
            "comment_id": "c1",
            "author": "Sara",
            "comment": "Hello",
            "ai_reply": "Hi Sara",
            "created_at": "",
            "delivery_status": "sent",
        }
    ]


def test_tiktok_includes_unreplied_comments() -> None:
    threads = pair_tiktok_threads(
        [
            {"post_id": "v1", "comment_id": "t1", "text": "Cute", "author_username": "a", "delivery_status": "none"},
            {
                "post_id": "v1",
                "comment_id": "t2",
                "text": "Price",
                "author_username": "b",
                "ai_reply": "See bio",
                "delivery_status": "sent",
            },
            {"post_id": "v2", "comment_id": "skip", "text": "other"},
            {"post_id": "v1", "comment_id": "child", "parent_comment_id": "t1", "text": "reply"},
        ],
        post_id="v1",
        limit=50,
    )
    assert [row["comment"] for row in threads] == ["Cute", "Price"]
    assert threads[0]["ai_reply"] == ""
    assert threads[1]["ai_reply"] == "See bio"


def test_instagram_login_threads_use_instagram_graph_version() -> None:
    class _Binding:
        auth_flow = "instagram_login"
        app_key = "app_a"

    assert graph_api_version_for_binding(_Binding()) == INSTAGRAM_LOGIN_GRAPH_API_VERSION
