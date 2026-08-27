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
