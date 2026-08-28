"""Durable turn + delivery ledger recovery without regenerating or double-send."""

from __future__ import annotations

import fakeredis
import pytest

from services.ai_reply_delivery import wrap_tracked_send
from services.ai_reply_lifecycle import begin_turn, find_pending_delivery_turn, persist_generated_reply
from services.scale.delivery_ledger import (
    begin_send,
    confirm_sent,
    mark_unknown,
    set_delivery_redis_for_tests,
    snapshot,
)
from services.scale.turn_store import set_turn_redis_for_tests


def setup_function() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_turn_redis_for_tests(fake)
    set_delivery_redis_for_tests(fake)


def teardown_function() -> None:
    set_turn_redis_for_tests(None)
    set_delivery_redis_for_tests(None)


def test_saved_reply_survives_process_wipe() -> None:
    turn = begin_turn(tenant_id="t1", channel="instagram", external_inbound_id="mid-1", claim_key_basis="claim-1")
    persist_generated_reply(turn.logical_reply_id, reply_text="hello from tera")
    pending = find_pending_delivery_turn(claim_key_basis="claim-1")
    assert pending is not None
    assert pending.generated_reply == "hello from tera"
    assert pending.state == "REPLY_PERSISTED"


def test_started_send_becomes_unknown_and_is_not_resent() -> None:
    key = "lr_delivery_1"
    assert begin_send(key) == "send"
    mark_unknown(key)
    assert begin_send(key) == "skip_unknown"
    assert snapshot(key)["state"] == "unknown"


def test_confirmed_send_is_not_resent() -> None:
    key = "lr_delivery_2"
    assert begin_send(key) == "send"
    confirm_sent(key, provider_message_id="mid_provider")
    assert begin_send(key) == "skip_sent"


@pytest.mark.asyncio
async def test_wrap_skips_unknown_without_calling_provider() -> None:
    calls: list[str] = []

    async def raw(_to: str, message_text: str | None = None, **_k: object) -> dict:
        calls.append(str(message_text))
        return {"success": True, "message_id": "mid_1"}

    user_data = {"_logical_reply_id": "lr_wrap_unknown"}
    begin_send("lr_wrap_unknown")
    mark_unknown("lr_wrap_unknown")
    tracked = wrap_tracked_send(raw, user_data)
    result = await tracked("user", message_text="hi")
    assert calls == []
    assert result.get("needs_owner_action") is True


@pytest.mark.asyncio
async def test_wrap_skips_already_sent() -> None:
    calls: list[str] = []

    async def raw(_to: str, message_text: str | None = None, **_k: object) -> dict:
        calls.append(str(message_text))
        return {"success": True, "message_id": "mid_new"}

    user_data = {"_logical_reply_id": "lr_wrap_sent"}
    begin_send("lr_wrap_sent")
    confirm_sent("lr_wrap_sent", provider_message_id="mid_old")
    tracked = wrap_tracked_send(raw, user_data)
    result = await tracked("user", message_text="hi")
    assert calls == []
    assert result.get("success") is True
    assert result.get("message_id") == "mid_old"


@pytest.mark.asyncio
async def test_nested_wrap_still_calls_provider_once() -> None:
    calls: list[str] = []

    async def raw(_to: str, message_text: str | None = None, **_k: object) -> dict:
        calls.append(str(message_text))
        return {"success": True, "provider": "meta", "message_id": "mid_nested"}

    user_data = {"_logical_reply_id": "lr_wrap_nested"}
    inner = wrap_tracked_send(raw, user_data)
    outer = wrap_tracked_send(inner, user_data)
    result = await outer("user", message_text="hello")
    assert outer is inner
    assert calls == ["hello"]
    assert result.get("success") is True
    assert result.get("message_id") == "mid_nested"
    assert snapshot("lr_wrap_nested")["state"] == "sent"
