"""Customer DM burst debounce: one Terra turn for rapid inbound fragments."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import config
from services.brain.inbound.burst_buffer import join_burst_texts, reset_flushing_for_tests
from services.brain.inbound.text_handlers_combine import schedule_combined_turn
from services.brain.inbound.text_handlers_firestore import _delayed_processing_tasks


def setup_function() -> None:
    reset_flushing_for_tests()


def teardown_function() -> None:
    reset_flushing_for_tests()


def test_join_burst_keeps_history_lines() -> None:
    assert join_burst_texts(["hi"]) == "hi"
    assert join_burst_texts(["hi", "price?"]) == "- hi\n- price?"


def _user(user_id: str) -> dict[str, Any]:
    return {
        "channel": "web_chat",
        "phone_number": f"room:{user_id}",
        "tenant_id": "t-burst",
    }


async def _noop_send(*_a: object, **_k: object) -> dict[str, Any]:
    return {"success": True}


async def _await_user_tasks(user_id: str, *, timeout: float = 2.0) -> None:
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        task = _delayed_processing_tasks.get(user_id)
        if task is None or task.done():
            await asyncio.sleep(0.02)
            nxt = _delayed_processing_tasks.get(user_id)
            if nxt is None or nxt.done():
                return
            task = nxt
        remaining = deadline - asyncio.get_event_loop().time()
        try:
            await asyncio.wait_for(task, timeout=max(0.05, remaining))
        except asyncio.CancelledError:
            continue


@pytest.mark.asyncio
async def test_two_quick_texts_one_brain_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.scale.message_combine_policy.durable_flush_jobs_enabled", lambda: False)
    monkeypatch.setattr("services.scale.message_combine_store.combine_redis_available", lambda: False)
    monkeypatch.setattr("services.brain.ai_reply.ai_reply_turn_runtime.try_reserve_for_ai", lambda *_a, **_k: True)
    processed: list[str] = []

    async def capture(_user_id: str, **kwargs: Any) -> None:
        processed.append(str(kwargs["user_input_to_process"]))

    monkeypatch.setattr("services.brain.inbound.text_handlers_delayed._process_and_respond", capture)
    user_id = "web:burst-quick"
    config.user_pending_messages[user_id].clear()
    user_data = _user(user_id)
    try:
        await schedule_combined_turn(
            user_id=user_id,
            raw_msg="hi",
            user_data=user_data,
            send_message_func=_noop_send,
            send_action_func=_noop_send,
            message_combine_delay=0.05,
        )
        await schedule_combined_turn(
            user_id=user_id,
            raw_msg="and the price please",
            user_data=user_data,
            send_message_func=_noop_send,
            send_action_func=_noop_send,
            message_combine_delay=0.05,
        )
        await _await_user_tasks(user_id)
        assert len(processed) == 1, processed
        assert "hi" in processed[0]
        assert "price" in processed[0]
    finally:
        config.user_pending_messages.pop(user_id, None)
        _delayed_processing_tasks.pop(user_id, None)


@pytest.mark.asyncio
async def test_slow_second_message_is_separate_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.scale.message_combine_policy.durable_flush_jobs_enabled", lambda: False)
    monkeypatch.setattr("services.scale.message_combine_store.combine_redis_available", lambda: False)
    monkeypatch.setattr("services.brain.ai_reply.ai_reply_turn_runtime.try_reserve_for_ai", lambda *_a, **_k: True)
    processed: list[str] = []

    async def capture(_user_id: str, **kwargs: Any) -> None:
        processed.append(str(kwargs["user_input_to_process"]))

    monkeypatch.setattr("services.brain.inbound.text_handlers_delayed._process_and_respond", capture)
    user_id = "web:burst-slow"
    config.user_pending_messages[user_id].clear()
    user_data = _user(user_id)
    try:
        await schedule_combined_turn(
            user_id=user_id,
            raw_msg="first",
            user_data=user_data,
            send_message_func=_noop_send,
            send_action_func=_noop_send,
            message_combine_delay=0.0,
        )
        await _await_user_tasks(user_id)
        await schedule_combined_turn(
            user_id=user_id,
            raw_msg="second later",
            user_data=user_data,
            send_message_func=_noop_send,
            send_action_func=_noop_send,
            message_combine_delay=0.0,
        )
        await _await_user_tasks(user_id)
        assert processed == ["first", "second later"]
    finally:
        config.user_pending_messages.pop(user_id, None)
        _delayed_processing_tasks.pop(user_id, None)


@pytest.mark.asyncio
async def test_no_parallel_terra_while_flushing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.scale.message_combine_policy.durable_flush_jobs_enabled", lambda: False)
    monkeypatch.setattr("services.scale.message_combine_store.combine_redis_available", lambda: False)
    monkeypatch.setattr("services.brain.ai_reply.ai_reply_turn_runtime.try_reserve_for_ai", lambda *_a, **_k: True)
    processed: list[str] = []
    started = asyncio.Event()
    release = asyncio.Event()
    concurrent = 0
    max_concurrent = 0

    async def slow(_user_id: str, **kwargs: Any) -> None:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        processed.append(str(kwargs["user_input_to_process"]))
        started.set()
        await release.wait()
        concurrent -= 1

    monkeypatch.setattr("services.brain.inbound.text_handlers_delayed._process_and_respond", slow)
    user_id = "web:burst-lock"
    config.user_pending_messages[user_id].clear()
    user_data = _user(user_id)
    try:
        await schedule_combined_turn(
            user_id=user_id,
            raw_msg="one",
            user_data=user_data,
            send_message_func=_noop_send,
            send_action_func=_noop_send,
            message_combine_delay=0.0,
        )
        await started.wait()
        await schedule_combined_turn(
            user_id=user_id,
            raw_msg="two",
            user_data=user_data,
            send_message_func=_noop_send,
            send_action_func=_noop_send,
            message_combine_delay=0.0,
        )
        assert max_concurrent == 1
        assert processed == ["one"]
        release.set()
        await _await_user_tasks(user_id)
        assert max_concurrent == 1
        assert processed == ["one", "two"]
    finally:
        release.set()
        config.user_pending_messages.pop(user_id, None)
        _delayed_processing_tasks.pop(user_id, None)
