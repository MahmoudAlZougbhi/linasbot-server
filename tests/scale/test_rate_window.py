"""Redis bucket rates for autoscale ingress/complete."""

from __future__ import annotations

import fakeredis

from services.scale.rate_window import bump, set_rate_redis_for_tests, snapshot_rates


def test_snapshot_rates_from_bumps() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_rate_redis_for_tests(fake)
    try:
        bump("ingress", 20)
        bump("complete", 8)
        ingress, complete = snapshot_rates()
        assert ingress > complete
        assert ingress > 0
        assert complete > 0
    finally:
        set_rate_redis_for_tests(None)


def test_unknown_kind_is_ignored() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_rate_redis_for_tests(fake)
    try:
        bump("nope", 99)
        ingress, complete = snapshot_rates()
        assert ingress == 0.0
        assert complete == 0.0
    finally:
        set_rate_redis_for_tests(None)


def test_openai_ready_is_tracked_apart_from_complete() -> None:
    from services.scale.rate_window import snapshot_openai_ready

    fake = fakeredis.FakeRedis(decode_responses=True)
    set_rate_redis_for_tests(fake)
    try:
        bump("openai_ready", 12)
        bump("complete", 3)
        assert snapshot_openai_ready() > 0
        _ingress, complete = snapshot_rates()
        assert complete > 0
        assert snapshot_openai_ready() > complete
    finally:
        set_rate_redis_for_tests(None)
