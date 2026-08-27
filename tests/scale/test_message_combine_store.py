"""Redis combine buffer: atomic append, webhook replay, debounce generation."""

from __future__ import annotations

import fakeredis

from services.scale.message_combine_store import (
    append_chunk,
    current_generation,
    drain_if_due,
    generation_is_current,
    peek_pending,
    set_combine_redis_for_tests,
)


def setup_function() -> None:
    set_combine_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))


def teardown_function() -> None:
    set_combine_redis_for_tests(None)


def test_append_is_atomic_and_ordered() -> None:
    first = append_chunk("t:ig:u1", text="one", event_id="e1", delay_seconds=3)
    second = append_chunk("t:ig:u1", text="two", event_id="e2", delay_seconds=3)
    assert first["accepted"] is True
    assert second["accepted"] is True
    assert second["generation"] == first["generation"] + 1
    pending = peek_pending("t:ig:u1")
    assert [row["text"] for row in pending] == ["one", "two"]


def test_webhook_replay_does_not_append_twice() -> None:
    first = append_chunk("t:ig:u1", text="hello", event_id="mid-1", mid="mid-1", delay_seconds=3)
    replay = append_chunk("t:ig:u1", text="hello", event_id="mid-1", mid="mid-1", delay_seconds=3)
    assert first["duplicate"] is False
    assert replay["duplicate"] is True
    assert replay["generation"] == first["generation"]
    assert len(peek_pending("t:ig:u1")) == 1


def test_stale_generation_is_not_current() -> None:
    first = append_chunk("t:ig:u1", text="a", event_id="a", delay_seconds=3)
    append_chunk("t:ig:u1", text="b", event_id="b", delay_seconds=3)
    assert generation_is_current("t:ig:u1", int(first["generation"])) is False
    assert current_generation("t:ig:u1") == int(first["generation"]) + 1


def test_drain_waits_until_due() -> None:
    append_chunk("t:ig:u1", text="a", event_id="a", delay_seconds=3, now=100.0)
    assert drain_if_due("t:ig:u1", now=101.0) is None
    drained = drain_if_due("t:ig:u1", now=104.0)
    assert drained is not None
    assert [row["text"] for row in drained] == ["a"]
    assert drain_if_due("t:ig:u1", now=105.0) == []


def test_tenants_do_not_share_buffers() -> None:
    append_chunk("clinic:ig:u1", text="a", event_id="a", delay_seconds=0, now=1.0)
    append_chunk("linas:ig:u1", text="b", event_id="b", delay_seconds=0, now=1.0)
    left = drain_if_due("clinic:ig:u1", now=2.0)
    right = drain_if_due("linas:ig:u1", now=2.0)
    assert [row["text"] for row in left or []] == ["a"]
    assert [row["text"] for row in right or []] == ["b"]
