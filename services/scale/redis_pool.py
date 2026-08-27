"""Shared Redis client with a bounded connection pool, timeouts, and retry."""

from __future__ import annotations

import os
import threading
from typing import Any

_lock = threading.Lock()
_clients: dict[str, Any] = {}
_TEST_CLIENT: Any | None = None


def set_redis_client_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client
    reset_redis_pool_for_tests()


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def redis_client(*, decode_responses: bool = True) -> Any | None:
    """Return a process-wide Redis client, or None when Redis is not configured."""
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.queues.config import redis_url

    url = redis_url()
    if not url:
        return None
    key = f"{url}|{int(decode_responses)}"
    with _lock:
        cached = _clients.get(key)
        if cached is not None:
            return cached
        import redis

        pool = redis.ConnectionPool.from_url(
            url,
            decode_responses=decode_responses,
            max_connections=_int_env("LINAS_REDIS_MAX_CONNECTIONS", 50),
            socket_connect_timeout=_float_env("LINAS_REDIS_CONNECT_TIMEOUT", 1.5),
            socket_timeout=_float_env("LINAS_REDIS_SOCKET_TIMEOUT", 1.5),
            retry_on_timeout=True,
        )
        client = redis.Redis(connection_pool=pool)
        _clients[key] = client
        return client


def reset_redis_pool_for_tests() -> None:
    with _lock:
        _clients.clear()
