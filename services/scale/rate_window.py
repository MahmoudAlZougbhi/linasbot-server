"""Cluster-wide ingress/complete rates from Redis time buckets."""

from __future__ import annotations

import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_SCALE_CTRL_PREFIX") or "linas:scale").strip() or "linas:scale"
_WINDOW_SEC = 10
_TEST_CLIENT: Any | None = None


def set_rate_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def bump(kind: str, n: int = 1) -> None:
    if kind not in {"ingress", "complete"} or n < 1:
        return
    client = _client()
    if client is None:
        return
    bucket = int(time.time() // _WINDOW_SEC)
    key = f"{_PREFIX}:rate:{kind}:{bucket}"
    try:
        pipe = client.pipeline()
        pipe.incrby(key, int(n))
        pipe.expire(key, _WINDOW_SEC * 3)
        pipe.execute()
    except Exception:
        return


def snapshot_rates() -> tuple[float, float]:
    """Return (ingress_per_sec, complete_per_sec) over the last ~10–20 seconds."""
    client = _client()
    if client is None:
        return 0.0, 0.0
    now = time.time()
    bucket = int(now // _WINDOW_SEC)
    elapsed = _WINDOW_SEC + (now % _WINDOW_SEC)
    if elapsed <= 0:
        return 0.0, 0.0
    try:
        ingress = _count(client, "ingress", bucket) + _count(client, "ingress", bucket - 1)
        complete = _count(client, "complete", bucket) + _count(client, "complete", bucket - 1)
    except Exception:
        return 0.0, 0.0
    return float(ingress) / elapsed, float(complete) / elapsed


def _count(client: Any, kind: str, bucket: int) -> int:
    raw = client.get(f"{_PREFIX}:rate:{kind}:{bucket}")
    try:
        return max(0, int(raw or 0))
    except (TypeError, ValueError):
        return 0
