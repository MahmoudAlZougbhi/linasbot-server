"""user_context deque is optional; Redis session keeps turn-critical fields."""

from __future__ import annotations

import fakeredis

import config
from services.scale.conversation_session import hydrate_into_process, persist_from_process, set_session_redis_for_tests
from tests.scale.process_local import wipe_process_conversation_state


def setup_function() -> None:
    set_session_redis_for_tests(fakeredis.FakeRedis(decode_responses=True))
    wipe_process_conversation_state()


def teardown_function() -> None:
    set_session_redis_for_tests(None)
    wipe_process_conversation_state()


def test_cache_miss_rebuilds_from_shared_session() -> None:
    user_id = "ig:u-cache"
    hydrate_into_process(user_id)
    config.user_data_whatsapp[user_id]["current_conversation_id"] = "conv-shared"
    config.user_data_whatsapp[user_id]["user_preferred_lang"] = "fr"
    config.user_names[user_id] = "Nour"
    config.user_in_human_takeover_mode[user_id] = True
    config.user_booking_state[user_id] = {"service": "laser"}
    config.user_context[user_id].append("local-only-history")
    persist_from_process(user_id)
    wipe_process_conversation_state()
    assert user_id not in config.user_context
    hydrate_into_process(user_id)
    assert config.user_data_whatsapp[user_id]["current_conversation_id"] == "conv-shared"
    assert config.user_data_whatsapp[user_id]["user_preferred_lang"] == "fr"
    assert config.user_names[user_id] == "Nour"
    assert config.user_in_human_takeover_mode[user_id] is True
    assert config.user_booking_state[user_id]["service"] == "laser"
    assert list(config.user_context[user_id]) == []
