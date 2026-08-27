"""Soak arm requires both Redis TTL and the job payload flag."""

from __future__ import annotations

from types import SimpleNamespace

import fakeredis

from services.scale.soak_arm import arm, disarm, is_armed, job_requests_soak_simulation, set_soak_redis_for_tests


def test_payload_alone_does_not_enable_simulation() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_soak_redis_for_tests(fake)
    try:
        job = SimpleNamespace(payload={"_linas_soak_simulation": True})
        assert is_armed() is False
        assert job_requests_soak_simulation(job) is False
    finally:
        set_soak_redis_for_tests(None)


def test_armed_payload_enables_simulation() -> None:
    fake = fakeredis.FakeRedis(decode_responses=True)
    set_soak_redis_for_tests(fake)
    try:
        arm(ttl_seconds=60)
        assert is_armed() is True
        on = SimpleNamespace(payload={"_linas_soak_simulation": True})
        off = SimpleNamespace(payload={})
        assert job_requests_soak_simulation(on) is True
        assert job_requests_soak_simulation(off) is False
        disarm()
        assert job_requests_soak_simulation(on) is False
    finally:
        set_soak_redis_for_tests(None)
