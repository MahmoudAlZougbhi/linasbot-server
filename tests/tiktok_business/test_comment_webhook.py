"""TikTok COMMENT webhooks enqueue visitor comments on any video."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from tests.tiktok_business.conftest import seed_connection


def _now_epoch() -> str:
    return str(int(datetime.now(UTC).timestamp()) + 120)


@pytest.mark.asyncio
async def test_comment_update_queues_visitor_on_any_video(tt_db, monkeypatch) -> None:
    connection = seed_connection(tt_db, open_id="biz-open")
    queued: list[dict] = []

    def _enqueue(**kwargs):
        queued.append(kwargs)

    async def _token(*_a, **_k):
        return "tok"

    async def _fetch(**_k):
        return {
            "comment_id": "c-new",
            "text": "hi",
            "owner": False,
            "unique_identifier": "visitor",
            "username": "visitor_tt",
            "create_time": _now_epoch(),
        }

    monkeypatch.setattr("services.tiktok_business.comment_webhook.enqueue_tiktok_comment_ai", _enqueue)
    monkeypatch.setattr("services.tiktok_business.comment_webhook.ensure_fresh_token", _token)
    monkeypatch.setattr("services.tiktok_business.comment_webhook._fetch_public_comment", _fetch)
    from services.tiktok_business.webhook_process import process_tiktok_webhook_payload

    payload = {
        "event": "comment.update",
        "event_id": "evt-c1",
        "user_openid": "biz-open",
        "content": json.dumps(
            {
                "comment_id": "c-new",
                "video_id": "vid-old",
                "parent_comment_id": 0,
                "comment_type": "comment",
                "comment_action": "insert",
            }
        ),
    }
    result = await process_tiktok_webhook_payload(raw_body=json.dumps(payload).encode(), payload=payload)
    assert result.get("queued") is True
    assert queued == [
        {
            "tenant_id": "linas",
            "connection_id": connection.id,
            "comment_id": "c-new",
            "item_id": "vid-old",
        }
    ]


@pytest.mark.asyncio
async def test_comment_update_skips_owner_and_replies(tt_db, monkeypatch) -> None:
    seed_connection(tt_db, open_id="biz-open")
    queued: list[dict] = []
    monkeypatch.setattr(
        "services.tiktok_business.comment_webhook.enqueue_tiktok_comment_ai", lambda **k: queued.append(k)
    )

    async def _token(*_a, **_k):
        return "tok"

    async def _fetch_owner(**_k):
        return {
            "comment_id": "c-owner",
            "text": "me",
            "owner": True,
            "create_time": _now_epoch(),
        }

    monkeypatch.setattr("services.tiktok_business.comment_webhook.ensure_fresh_token", _token)
    monkeypatch.setattr("services.tiktok_business.comment_webhook._fetch_public_comment", _fetch_owner)
    from services.tiktok_business.webhook_process import process_tiktok_webhook_payload

    owner_payload = {
        "event": "comment.update",
        "event_id": "evt-owner",
        "user_openid": "biz-open",
        "content": {
            "comment_id": "c-owner",
            "video_id": "vid-1",
            "parent_comment_id": 0,
            "comment_action": "insert",
        },
    }
    owner = await process_tiktok_webhook_payload(raw_body=b"{}", payload=owner_payload)
    assert owner.get("skipped") is True
    assert queued == []

    reply_payload = {
        "event": "comment.update",
        "event_id": "evt-reply",
        "user_openid": "biz-open",
        "content": {
            "comment_id": "c-reply",
            "video_id": "vid-1",
            "parent_comment_id": "c-parent",
            "comment_type": "reply",
            "comment_action": "insert",
        },
    }
    reply = await process_tiktok_webhook_payload(raw_body=b"{}", payload=reply_payload)
    assert reply.get("reason") == "reply"
    assert queued == []


@pytest.mark.asyncio
async def test_ensure_comment_webhook_skips_when_url_matches(monkeypatch) -> None:
    calls: list[str] = []

    async def _req(*, method: str, path: str, **_k):
        calls.append(f"{method}:{path}")
        return {"callback_url": "https://www.linasaibot.com/webhooks/tiktok"}

    monkeypatch.setenv("TIKTOK_CLIENT_KEY", "tt-client-key")
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    monkeypatch.setattr("services.tiktok_business.webhook_subscription.tiktok_request", _req)
    from services.tiktok_business.webhook_subscription import ensure_comment_webhook_registered

    result = await ensure_comment_webhook_registered()
    assert result["already"] is True
    assert calls == ["GET:/business/webhook/list/"]


def test_upsert_media_does_not_blank_existing_caption(tt_db) -> None:
    from services.tiktok_business.repository_content import TikTokContentRepository

    connection = seed_connection(tt_db)
    content = TikTokContentRepository(tt_db)
    first = content.upsert_media(tenant_id="linas", connection_id=connection.id, item_id="v-keep", caption="keep me")
    tt_db.commit()
    again = content.upsert_media(tenant_id="linas", connection_id=connection.id, item_id="v-keep")
    tt_db.commit()
    assert first.id == again.id
    assert again.caption == "keep me"
