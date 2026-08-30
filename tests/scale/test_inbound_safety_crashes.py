"""Crash and fence faults on Meta Graph send, soak skip, and credit-once."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import fakeredis
import pytest

import services.meta_outbound_attempts as attempts
from services.queues.meta_inbound_soak_gate import maybe_finish_soak_at_openai_gate
from services.scale.soak_arm import is_armed, job_requests_soak_simulation, set_soak_redis_for_tests
from tests.meta_compliance_helpers import _FakeFirestore


@pytest.fixture()
def outbound_store(monkeypatch: pytest.MonkeyPatch) -> _FakeFirestore:
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    return db


def teardown_function() -> None:
    set_soak_redis_for_tests(None)


@pytest.mark.asyncio
async def test_comment_public_and_private_sends_are_independent(outbound_store: _FakeFirestore) -> None:
    public_calls = 0
    private_calls = 0

    async def send_public() -> dict[str, Any]:
        nonlocal public_calls
        public_calls += 1
        return {"success": True, "provider": "meta", "message_id": "pub-1"}

    async def send_private() -> dict[str, Any]:
        nonlocal private_calls
        private_calls += 1
        return {"success": True, "provider": "meta", "message_id": "priv-1"}

    event_id = "ibe_" + "f" * 40
    first_public = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        purpose="primary_reply",
        send=send_public,
    )
    first_private = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        purpose="comment_private_dm",
        send=send_private,
    )
    dup_public = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        purpose="primary_reply",
        send=send_public,
    )
    dup_private = await attempts.execute_guarded_meta_send(
        event_id=event_id,
        surface="facebook_comment",
        purpose="comment_private_dm",
        send=send_private,
    )
    assert first_public["success"] is True
    assert first_private["success"] is True
    assert dup_public["duplicate_suppressed"] is True
    assert dup_private["duplicate_suppressed"] is True
    assert public_calls == 1
    assert private_calls == 1


@pytest.mark.asyncio
async def test_graph_accept_crash_before_sent_record_does_not_resend(
    outbound_store: _FakeFirestore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0
    real_finish = attempts.finish_meta_outbound_attempt

    async def send() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"success": True, "provider": "meta", "message_id": "graph-ok"}

    async def crash_accepted(*args: Any, **kwargs: Any) -> None:
        if kwargs.get("status") == "accepted":
            raise RuntimeError("killed after Graph accept")
        await real_finish(*args, **kwargs)

    monkeypatch.setattr(attempts, "finish_meta_outbound_attempt", crash_accepted)
    result = await attempts.execute_guarded_meta_send(
        event_id="ibe_" + "c" * 40,
        surface="instagram_dm",
        send=send,
    )
    assert result.get("needs_owner_action") is True
    monkeypatch.setattr(attempts, "finish_meta_outbound_attempt", real_finish)
    retry = await attempts.execute_guarded_meta_send(
        event_id="ibe_" + "c" * 40,
        surface="instagram_dm",
        send=send,
    )
    assert retry.get("needs_owner_action") is True
    assert calls == 1


def test_soak_openai_gate_requires_armed_redis() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_soak_redis_for_tests(fake)
    job = SimpleNamespace(payload={"_linas_soak_simulation": True, "event_id": "ibe_z", "kind": "meta_dm"})
    assert is_armed() is False
    assert job_requests_soak_simulation(job) is False
    assert maybe_finish_soak_at_openai_gate(soak=False, kind="meta_dm", event_id="ibe_z") is None
    fake.setex("linas:scale:soak_simulation", 60, "1")
    assert job_requests_soak_simulation(job) is True
    done = maybe_finish_soak_at_openai_gate(soak=True, kind="meta_dm", event_id="ibe_z")
    assert done is not None
    assert done["openai_gate"] is True


def test_pending_delivery_reuses_saved_reply(monkeypatch: pytest.MonkeyPatch) -> None:
    import fakeredis

    from services.ai_reply_lifecycle import begin_turn, find_pending_delivery_turn, persist_generated_reply
    from services.scale.turn_store import set_turn_redis_for_tests

    fake = fakeredis.FakeRedis(decode_responses=True)
    set_turn_redis_for_tests(fake)
    try:
        turn = begin_turn(
            tenant_id="linas",
            channel="facebook",
            external_inbound_id="mid-save",
            claim_key_basis="face:mid-save",
        )
        persist_generated_reply(turn.logical_reply_id, reply_text="one generation")
        pending = find_pending_delivery_turn(claim_key_basis="face:mid-save")
        assert pending is not None
        assert pending.generated_reply == "one generation"
        again = find_pending_delivery_turn(claim_key_basis="face:mid-save")
        assert again is not None
        assert again.logical_reply_id == turn.logical_reply_id
    finally:
        set_turn_redis_for_tests(None)
