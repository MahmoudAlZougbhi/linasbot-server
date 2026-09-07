"""A/H/I: comments still work without enhanced permission; no reply / idempotency."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.tiktok_business.comment_ai import process_tiktok_comment_ai
from services.tiktok_business.repository_content import TikTokContentRepository
from tests.tiktok_business.conftest import seed_connection


def _seed_comment(session, *, comment_id: str, item_id: str = "v1"):
    connection = seed_connection(session)
    content = TikTokContentRepository(session)
    media = content.upsert_media(tenant_id="linas", connection_id=connection.id, item_id=item_id, caption="laser offer")
    content.upsert_comment(
        tenant_id="linas",
        connection_id=connection.id,
        media=media,
        payload={"comment_id": comment_id, "text": "what is this"},
    )
    session.commit()
    return connection


@pytest.mark.asyncio
async def test_a_comments_work_without_identity_http(tt_db, monkeypatch) -> None:
    connection = _seed_comment(tt_db, comment_id="c-basic")
    hits: list[str] = []

    async def _identity(**_k):
        hits.append("identity")
        raise AssertionError("identity must not run without advertiser token")

    async def _resolve(**kwargs):
        assert kwargs["account_token"] == "tok"
        return {
            "comment_context": {
                "caption": "laser offer",
                "context_level": "caption_thumbnail",
                "tiktok_raw_video": False,
            },
            "caption": "laser offer",
            "context_level": "caption_thumbnail",
            "diagnostics": {"reason_code": "authorization_required"},
        }

    async def _reply(**kwargs):
        assert kwargs["caption"] == "laser offer"
        assert kwargs["comment_context"]["context_level"] == "caption_thumbnail"
        return SimpleNamespace(
            stop=True,
            reply="this is our laser offer",
            reason="v2_comment_generated",
            metadata={"model": "m", "tokens": 2, "cost_usd": 0.0},
        )

    async def _publish(**_k):
        return {"request_id": "req-basic", "comment_id": "reply-basic"}

    monkeypatch.setattr("services.tiktok_business.comment_ai.comments_action_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ai_generation_blocked", lambda *_a, **_k: False)
    monkeypatch.setattr("services.tiktok_business.comment_ai.resolve_tiktok_post_context", _resolve)
    monkeypatch.setattr("services.tiktok_business.comment_ai.run_customer_reply_v2_comment", _reply)
    monkeypatch.setattr("services.tiktok_business.comment_ai.create_comment_reply", _publish)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ensure_fresh_token", _tok)
    monkeypatch.setattr("services.tiktok_business.post_context.identity_video_info", _identity)
    ok = await process_tiktok_comment_ai(
        tenant_id="linas", connection_id=connection.id, comment_id="c-basic", item_id="v1"
    )
    assert ok["ok"] is True
    assert hits == []


async def _tok(*_a, **_k):
    return "tok"


@pytest.mark.asyncio
async def test_h_no_confident_reply_does_not_publish(tt_db, monkeypatch) -> None:
    connection = _seed_comment(tt_db, comment_id="c-empty")
    published = {"called": False}

    async def _resolve(**_k):
        return {
            "comment_context": {"caption": "laser offer", "context_level": "caption_thumbnail"},
            "caption": "laser offer",
            "context_level": "caption_thumbnail",
            "diagnostics": {},
        }

    async def _reply(**_k):
        return SimpleNamespace(stop=True, reply="", reason="no_confident_reply", metadata={})

    async def _publish(**_k):
        published["called"] = True
        return {}

    monkeypatch.setattr("services.tiktok_business.comment_ai.comments_action_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ai_generation_blocked", lambda *_a, **_k: False)
    monkeypatch.setattr("services.tiktok_business.comment_ai.resolve_tiktok_post_context", _resolve)
    monkeypatch.setattr("services.tiktok_business.comment_ai.run_customer_reply_v2_comment", _reply)
    monkeypatch.setattr("services.tiktok_business.comment_ai.create_comment_reply", _publish)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ensure_fresh_token", _tok)
    result = await process_tiktok_comment_ai(
        tenant_id="linas", connection_id=connection.id, comment_id="c-empty", item_id="v1"
    )
    assert result["skipped"] is True
    assert result["reason"] == "no_confident_reply"
    assert published["called"] is False


@pytest.mark.asyncio
async def test_i_duplicate_job_does_not_double_reply(tt_db, monkeypatch) -> None:
    connection = _seed_comment(tt_db, comment_id="c-dup")
    content = TikTokContentRepository(tt_db)
    job, _ = content.get_or_create_reply_job(tenant_id="linas", connection_id=connection.id, comment_id="c-dup")
    job.delivery_status = "sent"
    tt_db.commit()
    result = await process_tiktok_comment_ai(
        tenant_id="linas", connection_id=connection.id, comment_id="c-dup", item_id="v1"
    )
    assert result["skipped"] is True
    assert result["reason"] == "already_handled"
