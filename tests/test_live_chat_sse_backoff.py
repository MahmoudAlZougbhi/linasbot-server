from __future__ import annotations

from services.live_chat.sse_broadcaster import next_pubsub_backoff, pubsub_log_due


def test_backoff_doubles_until_one_minute() -> None:
    delay = 0.0
    seen = []
    for _ in range(8):
        delay = next_pubsub_backoff(delay)
        seen.append(delay)
    assert seen[:3] == [2.0, 4.0, 8.0]
    assert seen[-1] == 60.0


def test_reconnect_log_is_once_per_minute() -> None:
    assert pubsub_log_due(-60.0, 0.0) is True
    assert pubsub_log_due(10.0, 69.0) is False
    assert pubsub_log_due(10.0, 70.0) is True
