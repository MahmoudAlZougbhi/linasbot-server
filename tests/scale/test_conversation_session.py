"""Node 1 / node 2 / node 3 must share conversation session via Redis."""

from __future__ import annotations

import fakeredis

import config
from services.scale.conversation_session import (
    hydrate_into_process,
    persist_from_process,
    set_session_redis_for_tests,
)
from services.scale.message_combine_store import append_chunk, drain_if_due, set_combine_redis_for_tests
from tests.scale.process_local import wipe_process_conversation_state


def setup_function() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_session_redis_for_tests(fake)
    set_combine_redis_for_tests(fake)
    wipe_process_conversation_state()


def teardown_function() -> None:
    set_session_redis_for_tests(None)
    set_combine_redis_for_tests(None)
    wipe_process_conversation_state()


def test_three_nodes_keep_one_conversation() -> None:
    user_id = "ig:u-session-1"

    # Node 1 receives message 1 and stores conversation continuity.
    hydrate_into_process(user_id)
    config.user_data_whatsapp[user_id]["current_conversation_id"] = "conv-99"
    config.user_data_whatsapp[user_id]["user_preferred_lang"] = "ar"
    config.user_data_whatsapp[user_id]["_conversation_key"] = "t1:instagram:ig:u-session-1"
    config.user_names[user_id] = "Lina"
    persist_from_process(user_id)
    first = append_chunk(user_id, text="hello", event_id="e1", delay_seconds=3, now=100.0)
    assert first["accepted"] is True
    wipe_process_conversation_state()

    # Node 2 receives message 2 with empty process memory.
    assert user_id not in config.user_data_whatsapp
    hydrate_into_process(user_id)
    assert config.user_data_whatsapp[user_id]["current_conversation_id"] == "conv-99"
    assert config.user_names[user_id] == "Lina"
    second = append_chunk(user_id, text="there", event_id="e2", delay_seconds=3, now=100.4)
    assert second["accepted"] is True
    persist_from_process(user_id)
    wipe_process_conversation_state()

    # Node 3 runs the combine job.
    hydrate_into_process(user_id)
    chunks = drain_if_due(user_id, now=104.0)
    assert chunks is not None
    assert [row["text"] for row in chunks] == ["hello", "there"]
    assert config.user_data_whatsapp[user_id]["current_conversation_id"] == "conv-99"


def test_same_webhook_on_two_nodes_appends_once() -> None:
    user_id = "ig:u-dup"
    a = append_chunk(user_id, text="hi", event_id="mid-9", delay_seconds=3, now=1.0)
    wipe_process_conversation_state()
    b = append_chunk(user_id, text="hi", event_id="mid-9", delay_seconds=3, now=1.1)
    assert a["duplicate"] is False
    assert b["duplicate"] is True
