"""HA and dedup tests for Meta social comment polling sync."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.meta_cross_flow_dedup import global_comment_claim_key
from services.meta_social_comment_sync import _enqueue_comment_ai, sync_facebook_binding_comments


def _facebook_binding() -> object:
    return type(
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


@pytest.mark.asyncio
async def test_enqueue_comment_ai_skips_when_global_claim_already_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _facebook_binding()
    event = {
        "channel": "facebook",
        "comment_id": "comment_1",
        "post_id": "post_1",
        "account_id": "page_1",
        "text": "hello",
    }
    settings = type("S", (), {"graph_api_version": "v24.0"})()
    process = AsyncMock()

    monkeypatch.setattr(
        "services.durable_event_claim.try_claim_event_handle",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("services.meta_comment_replies.process_meta_comment_event", process)

    claimed = await _enqueue_comment_ai(binding=binding, settings=settings, event=event)

    assert claimed is False
    process.assert_not_awaited()
    assert global_comment_claim_key(event) == "facebook:page_1:comment_1"


@pytest.mark.asyncio
async def test_sync_facebook_binding_comments_pagination_seeds_backfill_from_recent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _facebook_binding()
    credential = type("C", (), {"access_token": "token", "scopes": frozenset()})()
    saved: list[str | None] = []

    monkeypatch.setattr("services.meta_social_comment_sync._binding_by_id", lambda _r, _id: binding)
    monkeypatch.setattr("services.meta_social_comment_sync._comment_reply_enabled", lambda _b: True)
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_configs",
        lambda: {"linas_first_party": type("A", (), {"graph_api_version": "v24.0"})()},
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_registry",
        lambda: type(
            "R",
            (),
            {"get_credential": lambda _self, _b: credential, "list_bindings": lambda *a, **k: []},
        )(),
    )
    monkeypatch.setattr("services.meta_social_comment_sync.load_posts_backfill_cursor", lambda _id: None)
    monkeypatch.setattr(
        "services.meta_social_comment_sync.save_posts_backfill_cursor",
        lambda _id, cursor: saved.append(cursor),
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.build_messaging_settings_for_binding",
        lambda *a, **k: type("S", (), {"graph_api_version": "v24.0", "page_access_token": "token"})(),
    )

    async def fake_graph(*args: object, **kwargs: object) -> dict[str, object]:
        return {
            "data": [{"id": "recent_post", "comments": {"data": []}}],
            "paging": {"next": "https://graph.facebook.com/page-2"},
        }

    with patch("services.meta_social_comment_sync._graph_get_json", new=AsyncMock(side_effect=fake_graph)) as graph:
        with patch("services.meta_social_comment_sync._enqueue_comment_ai", new=AsyncMock(return_value=False)):
            await sync_facebook_binding_comments("bind_1")

    assert graph.await_count == 1
    assert graph.await_args_list[0].kwargs.get("absolute_url") is None
    assert saved == ["https://graph.facebook.com/page-2"]


@pytest.mark.asyncio
async def test_poll_and_webhook_overlap_only_first_path_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    binding = _facebook_binding()
    credential = type("C", (), {"access_token": "token", "scopes": frozenset()})()
    claim_calls = 0
    process = AsyncMock(
        return_value=type("R", (), {"status": "sent", "reason": None})(),
    )

    async def claim_side_effect(*args: object, **kwargs: object) -> MagicMock | None:
        nonlocal claim_calls
        claim_calls += 1
        return MagicMock() if claim_calls == 1 else None

    monkeypatch.setattr("services.meta_social_comment_sync._binding_by_id", lambda _r, _id: binding)
    monkeypatch.setattr("services.meta_social_comment_sync._comment_reply_enabled", lambda _b: True)
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_configs",
        lambda: {"linas_first_party": type("A", (), {"graph_api_version": "v24.0"})()},
    )
    monkeypatch.setattr(
        "services.meta_social_comment_sync.get_meta_app_registry",
        lambda: type(
            "R",
            (),
            {"get_credential": lambda _self, _b: credential, "list_bindings": lambda *a, **k: []},
        )(),
    )
    monkeypatch.setattr("services.meta_social_comment_sync.load_posts_backfill_cursor", lambda _id: None)
    monkeypatch.setattr("services.meta_social_comment_sync.save_posts_backfill_cursor", lambda *_a: None)
    monkeypatch.setattr(
        "services.durable_event_claim.try_claim_event_handle",
        AsyncMock(side_effect=claim_side_effect),
    )
    monkeypatch.setattr("services.durable_event_claim.complete_event_claim", AsyncMock())
    monkeypatch.setattr("services.meta_comment_replies.process_meta_comment_event", process)
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
                            {"id": "comment_1", "message": "hello", "from": {"id": "user_1", "name": "U"}},
                        ]
                    },
                }
            ]
        }

    with patch("services.meta_social_comment_sync._graph_get_json", new=AsyncMock(side_effect=fake_graph)):
        result = await sync_facebook_binding_comments("bind_1")

    assert result["discovered"] == 2
    assert result["enqueued"] == 1
    process.assert_awaited_once()
