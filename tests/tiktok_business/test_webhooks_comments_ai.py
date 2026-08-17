"""Webhook signature, duplicate events, comments, replies, rate limits, credits."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime

import pytest

from services.tiktok_business.errors import TikTokApiError, TikTokBusinessError
from services.tiktok_business.http_client import is_retryable
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.webhook_verify import verify_tiktok_signature
from tests.tiktok_business.conftest import seed_connection


def _sign(secret: str, body: bytes, ts: int) -> str:
    signed = f"{ts}.".encode() + body
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return f"t={ts},s={digest}"


def test_webhook_signature_valid_and_invalid(monkeypatch) -> None:
    monkeypatch.setenv("TIKTOK_CLIENT_SECRET", "tt-client-secret-value")
    body = b'{"event":"im_receive_msg"}'
    header = _sign("tt-client-secret-value", body, int(time.time()))
    verify_tiktok_signature(raw_body=body, header=header)
    with pytest.raises(TikTokBusinessError, match="mismatch"):
        verify_tiktok_signature(raw_body=body, header=_sign("wrong", body, int(time.time())))
    with pytest.raises(TikTokBusinessError, match="stale"):
        verify_tiktok_signature(raw_body=body, header=_sign("tt-client-secret-value", body, int(time.time()) - 400))


@pytest.mark.asyncio
async def test_duplicate_webhook_and_gated_messaging(tt_db, monkeypatch) -> None:
    from services.tiktok_business.webhook_process import process_tiktok_webhook_payload

    seed_connection(tt_db, open_id="biz-1")
    payload = {
        "event": "im_receive_msg",
        "event_id": "evt-1",
        "user_openid": "biz-1",
        "content": {"conversation_id": "c1", "from": "cust-1", "text": "hi", "message_id": "m1"},
    }
    raw = json.dumps(payload).encode("utf-8")
    first = await process_tiktok_webhook_payload(raw_body=raw, payload=payload)
    assert first.get("gated") is True
    second = await process_tiktok_webhook_payload(raw_body=raw, payload=payload)
    assert second.get("duplicate") is True


def test_duplicate_comments_and_ai_claim(tt_db) -> None:
    connection = seed_connection(tt_db)
    content = TikTokContentRepository(tt_db)
    media = content.upsert_media(
        tenant_id="linas",
        connection_id=connection.id,
        item_id="video-1",
        caption="hello",
    )
    payload = {"comment_id": "cmt-1", "text": "price?", "user": {"display_name": "ada"}}
    row1, created1 = content.upsert_comment(
        tenant_id="linas", connection_id=connection.id, media=media, payload=payload
    )
    row2, created2 = content.upsert_comment(
        tenant_id="linas", connection_id=connection.id, media=media, payload=payload
    )
    tt_db.commit()
    assert created1 is True
    assert created2 is False
    assert row1.id == row2.id
    claimed = content.claim_comment_for_ai(tenant_id="linas", comment_id="cmt-1")
    assert claimed is not None
    again = content.claim_comment_for_ai(tenant_id="linas", comment_id="cmt-1")
    assert again is None


def test_duplicate_messages(tt_db) -> None:
    connection = seed_connection(tt_db)
    content = TikTokContentRepository(tt_db)
    conv = content.upsert_conversation(
        tenant_id="linas",
        connection_id=connection.id,
        conversation_id="conv-1",
        customer_open_id="cust-1",
        preview="hi",
        at=datetime.now(UTC),
    )
    _m1, created1 = content.insert_message(
        tenant_id="linas",
        connection_id=connection.id,
        conversation_row_id=conv.id,
        provider_message_id="mid-1",
        direction="inbound",
        text="hi",
    )
    _m2, created2 = content.insert_message(
        tenant_id="linas",
        connection_id=connection.id,
        conversation_row_id=conv.id,
        provider_message_id="mid-1",
        direction="inbound",
        text="hi",
    )
    assert created1 is True
    assert created2 is False


def test_retryable_rate_limit_codes() -> None:
    assert is_retryable(40100, 200) is True
    assert is_retryable(0, 429) is True
    assert is_retryable(40000, 400) is False
    err = TikTokApiError("slow", tiktok_code=40100, request_id="r1", retryable=True)
    assert err.retryable is True
    assert err.request_id == "r1"


@pytest.mark.asyncio
async def test_comment_ai_credits_and_success(tt_db, monkeypatch) -> None:
    from types import SimpleNamespace

    connection = seed_connection(tt_db)
    content = TikTokContentRepository(tt_db)
    media = content.upsert_media(tenant_id="linas", connection_id=connection.id, item_id="v1")
    content.upsert_comment(
        tenant_id="linas",
        connection_id=connection.id,
        media=media,
        payload={"comment_id": "c-credits", "text": "hi"},
    )
    tt_db.commit()
    monkeypatch.setattr("services.tiktok_business.comment_ai.comments_action_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ai_generation_blocked", lambda *_a, **_k: True)
    from services.tiktok_business.comment_ai import process_tiktok_comment_ai

    blocked = await process_tiktok_comment_ai(
        tenant_id="linas", connection_id=connection.id, comment_id="c-credits", item_id="v1"
    )
    assert blocked["reason"] == "insufficient_credits"

    content.upsert_comment(
        tenant_id="linas",
        connection_id=connection.id,
        media=media,
        payload={"comment_id": "c-ok", "text": "hi"},
    )
    tt_db.commit()
    monkeypatch.setattr("services.tiktok_business.comment_ai.ai_generation_blocked", lambda *_a, **_k: False)

    async def _reply(**_k):
        return SimpleNamespace(
            stop=False, reply="thanks", reason="ok", metadata={"model": "m", "tokens": 3, "cost_usd": 0.0}
        )

    async def _publish(**_k):
        return {"request_id": "req-9", "comment_id": "reply-9"}

    async def _token(*_a, **_k):
        return "tok"

    monkeypatch.setattr("services.tiktok_business.comment_ai.run_customer_reply_v2_comment", _reply)
    monkeypatch.setattr("services.tiktok_business.comment_ai.create_comment_reply", _publish)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ensure_fresh_token", _token)
    ok = await process_tiktok_comment_ai(
        tenant_id="linas", connection_id=connection.id, comment_id="c-ok", item_id="v1"
    )
    assert ok["ok"] is True
    assert ok["request_id"] == "req-9"


@pytest.mark.asyncio
async def test_comment_ai_publish_failure(tt_db, monkeypatch) -> None:
    from types import SimpleNamespace

    connection = seed_connection(tt_db)
    content = TikTokContentRepository(tt_db)
    media = content.upsert_media(tenant_id="linas", connection_id=connection.id, item_id="v2")
    content.upsert_comment(
        tenant_id="linas",
        connection_id=connection.id,
        media=media,
        payload={"comment_id": "c-fail", "text": "hi"},
    )
    tt_db.commit()
    monkeypatch.setattr("services.tiktok_business.comment_ai.comments_action_enabled", lambda *_a, **_k: True)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ai_generation_blocked", lambda *_a, **_k: False)

    async def _reply(**_k):
        return SimpleNamespace(stop=False, reply="thanks", reason="ok", metadata={})

    async def _publish(**_k):
        raise TikTokApiError("denied", tiktok_code=40001, request_id="req-fail", retryable=False)

    async def _token(*_a, **_k):
        return "tok"

    monkeypatch.setattr("services.tiktok_business.comment_ai.run_customer_reply_v2_comment", _reply)
    monkeypatch.setattr("services.tiktok_business.comment_ai.create_comment_reply", _publish)
    monkeypatch.setattr("services.tiktok_business.comment_ai.ensure_fresh_token", _token)
    from services.tiktok_business.comment_ai import process_tiktok_comment_ai

    result = await process_tiktok_comment_ai(
        tenant_id="linas", connection_id=connection.id, comment_id="c-fail", item_id="v2"
    )
    assert result["ok"] is False
    assert result["request_id"] == "req-fail"
