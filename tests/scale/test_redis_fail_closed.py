"""Redis required paths must fail closed — never pretend a job was stored locally."""

from __future__ import annotations

import pytest

from services.scale.message_combine_store import append_chunk, set_combine_redis_for_tests
from services.scale.turn_store import TurnStoreUnavailable, save_turn, set_turn_redis_for_tests, store_required


def teardown_function() -> None:
    set_combine_redis_for_tests(None)
    set_turn_redis_for_tests(None)


def test_combine_append_raises_when_client_errors(monkeypatch) -> None:
    class Boom:
        def sadd(self, *_a, **_k):
            raise RuntimeError("redis down")

        def expire(self, *_a, **_k):
            return True

    set_combine_redis_for_tests(Boom())
    with pytest.raises(RuntimeError, match="combine_append_failed"):
        append_chunk("u1", text="hi", event_id="e1", delay_seconds=1)


def test_turn_store_required_raises_without_client(monkeypatch) -> None:
    monkeypatch.setenv("LINAS_REQUIRE_REDIS", "true")
    set_turn_redis_for_tests(None)
    monkeypatch.setattr("services.scale.turn_store._client", lambda: None)
    monkeypatch.setattr("services.scale.turn_store.store_enabled", lambda: True)
    monkeypatch.setattr("services.scale.turn_store.store_required", lambda: True)
    with pytest.raises(TurnStoreUnavailable):
        save_turn({"logical_reply_id": "lr_x"})
    assert store_required() is True
