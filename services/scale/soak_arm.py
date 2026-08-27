"""Operator-armed soak switch: Redis TTL, not an env fallback."""

from __future__ import annotations

from typing import Any

_KEY = "linas:scale:soak_simulation"
_TEST_CLIENT: Any | None = None


def set_soak_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


_MAX_ARM_TTL_SECONDS = 4 * 60 * 60 + 900


def arm(*, ttl_seconds: int) -> None:
    client = _client()
    if client is None:
        raise RuntimeError("soak_arm_redis_unavailable")
    ttl = max(30, min(int(ttl_seconds), _MAX_ARM_TTL_SECONDS))
    client.setex(_KEY, ttl, "1")


def disarm() -> None:
    client = _client()
    if client is None:
        return
    client.delete(_KEY)


def is_armed() -> bool:
    client = _client()
    if client is None:
        return False
    try:
        return str(client.get(_KEY) or "") == "1"
    except Exception:
        return False


def job_requests_soak_simulation(job: Any) -> bool:
    payload = getattr(job, "payload", None)
    if not isinstance(payload, dict):
        return False
    if not bool(payload.get("_linas_soak_simulation")):
        return False
    return is_armed()
