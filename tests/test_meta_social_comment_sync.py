"""Tests for Meta social comment Graph polling sync."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.meta_social_comment_sync import _facebook_comment_events, sync_facebook_binding_comments


def test_facebook_comment_events_skip_page_self_replies() -> None:
    events = _facebook_comment_events(
        "post_1",
        [
            {"id": "c1", "message": "hi", "from": {"id": "user_1", "name": "User"}},
            {"id": "c2", "message": "page", "from": {"id": "page_1", "name": "Page"}},
        ],
        page_id="page_1",
    )
    assert len(events) == 1
    assert events[0]["comment_id"] == "c1"


def test_facebook_comment_events_include_nested_thread_replies() -> None:
    events = _facebook_comment_events(
        "post_1",
        [
            {
                "id": "c1",
                "message": "nice",
                "from": {"id": "user_1", "name": "User"},
                "comments": {
                    "data": [
                        {
                            "id": "c2",
                            "message": "Thank you!",
                            "from": {"id": "page_1", "name": "Page"},
                        },
                        {
                            "id": "c3",
                            "message": "follow up",
                            "from": {"id": "user_1", "name": "User"},
                        },
                    ]
                },
            }
        ],
        page_id="page_1",
    )
    assert [event["comment_id"] for event in events] == ["c1", "c3"]


@pytest.mark.asyncio
async def test_sync_facebook_binding_comments_enqueues_new_comment(monkeypatch: pytest.MonkeyPatch) -> None:
    binding = type(
        "B",
        (),
        {
            "binding_id": "bind_1",
            "active": True,
            "status": "active",
            "channel": "facebook",
            "app_key": "linas_first_party",
            "tenant_id": "linas",
            "page_id": "page_1",
            "asset_id": "page_1",
            "auth_flow": "facebook_login",
        },
    )()
    credential = type("C", (), {"access_token": "token", "scopes": frozenset()})()
    registry = type(
        "R",
        (),
        {
            "list_bindings": lambda *a, **k: [],
        },
    )()

    monkeypatch.setattr("services.meta_social_comment_sync._binding_by_id", lambda _r, _id: binding)
    monkeypatch.setattr("services.meta_social_comment_sync.get_meta_app_registry", lambda: registry)
    monkeypatch.setattr("services.meta_social_comment_sync._comment_reply_enabled", lambda _b: True)
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_configs",
        lambda: {"linas_first_party": type("A", (), {"graph_api_version": "v24.0"})()},
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_registry",
        lambda: type(
            "R2",
            (),
            {"get_credential": lambda _self, _b: credential, "list_bindings": lambda *a, **k: []},
        )(),
    )
    monkeypatch.setattr(
        "services.durable_event_claim.try_claim_event_handle",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "services.durable_event_claim.complete_event_claim",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.build_messaging_settings_for_binding",
        lambda *a, **k: type("S", (), {"graph_api_version": "v24.0", "page_access_token": "token"})(),
    )

    async def fake_graph(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "data": [
                {
                    "id": "post_1",
                    "comments": {
                        "data": [
                            {"id": "comment_1", "message": "hello", "from": {"id": "user_1", "name": "U"}},
                        ]
                    },
                }
            ]
        }

    with patch("services.meta_social_comment_sync._graph_get_json", new=AsyncMock(side_effect=fake_graph)):
        with patch(
            "services.meta_social_comment_sync._enqueue_comment_ai",
            new=AsyncMock(return_value=True),
        ) as enqueue:
            result = await sync_facebook_binding_comments("bind_1")
    assert result["enqueued"] == 1
    enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_facebook_binding_comments_always_scans_recent_posts_with_stale_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = type(
        "B",
        (),
        {
            "binding_id": "bind_1",
            "active": True,
            "status": "active",
            "channel": "facebook",
            "app_key": "linas_first_party",
            "tenant_id": "linas",
            "page_id": "page_1",
            "asset_id": "page_1",
            "auth_flow": "facebook_login",
        },
    )()
    credential = type("C", (), {"access_token": "token", "scopes": frozenset()})()

    monkeypatch.setattr("services.meta_social_comment_sync._binding_by_id", lambda _r, _id: binding)
    monkeypatch.setattr("services.meta_social_comment_sync._comment_reply_enabled", lambda _b: True)
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_configs",
        lambda: {"linas_first_party": type("A", (), {"graph_api_version": "v24.0"})()},
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_registry",
        lambda: type(
            "R2",
            (),
            {"get_credential": lambda _self, _b: credential, "list_bindings": lambda *a, **k: []},
        )(),
    )
    monkeypatch.setattr("services.meta_social_comment_sync.load_posts_cursor", lambda _id: "https://graph.facebook.com/old-page")
    saved_cursor: list[str | None] = []
    monkeypatch.setattr(
        "services.meta_social_comment_sync.save_posts_cursor",
        lambda _id, cursor: saved_cursor.append(cursor),
    )
    monkeypatch.setattr(
        "services.durable_event_claim.try_claim_event_handle",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(
        "services.durable_event_claim.complete_event_claim",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.build_messaging_settings_for_binding",
        lambda *a, **k: type("S", (), {"graph_api_version": "v24.0", "page_access_token": "token"})(),
    )

    async def fake_graph(*args: object, **kwargs: object) -> dict[str, object]:
        absolute_url = kwargs.get("absolute_url")
        if absolute_url:
            return {"data": [{"id": "old_post", "comments": {"data": []}}]}
        return {
            "data": [
                {
                    "id": "recent_post",
                    "comments": {
                        "data": [
                            {"id": "comment_1", "message": "hello", "from": {"id": "user_1", "name": "U"}},
                        ]
                    },
                }
            ],
            "paging": {"next": "https://graph.facebook.com/page-2"},
        }

    with patch("services.meta_social_comment_sync._graph_get_json", new=AsyncMock(side_effect=fake_graph)) as graph:
        with patch(
            "services.meta_social_comment_sync._enqueue_comment_ai",
            new=AsyncMock(return_value=True),
        ) as enqueue:
            result = await sync_facebook_binding_comments("bind_1")

    assert result["enqueued"] == 1
    enqueue.assert_awaited_once()
    assert graph.await_count == 2
    assert graph.await_args_list[0].kwargs.get("absolute_url") is None
    assert graph.await_args_list[1].kwargs.get("absolute_url") == "https://graph.facebook.com/old-page"
    assert saved_cursor == [""]
