"""Shared Redis latency histograms with percentile reads (p50/p90/p95/p99/max)."""

from __future__ import annotations

import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_HIST_PREFIX") or "linas:hist").strip() or "linas:hist"
_TTL_SEC = max(60, int(os.getenv("LINAS_HIST_TTL_SEC") or "3600"))
_MAX_SAMPLES = max(100, int(os.getenv("LINAS_HIST_MAX_SAMPLES") or "4000"))
_TEST_CLIENT: Any | None = None


def set_histogram_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def observe(metric: str, value_ms: float, *, now: float | None = None) -> None:
    name = "".join(c if c.isalnum() or c in "_:-" else "_" for c in metric)[:80]
    client = _client()
    if client is None:
        return
    ts = time.time() if now is None else float(now)
    member = f"{ts:.6f}:{value_ms:.3f}:{os.getpid()}"
    key = f"{_PREFIX}:{name}"
    try:
        pipe = client.pipeline()
        pipe.zadd(key, {member: float(value_ms)})
        pipe.zremrangebyrank(key, 0, -(_MAX_SAMPLES + 1))
        pipe.expire(key, _TTL_SEC)
        pipe.execute()
    except Exception:
        return


def percentiles(metric: str) -> dict[str, float]:
    name = "".join(c if c.isalnum() or c in "_:-" else "_" for c in metric)[:80]
    client = _client()
    empty = {"count": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    if client is None:
        return empty
    try:
        values = [float(score) for _member, score in client.zrange(f"{_PREFIX}:{name}", 0, -1, withscores=True)]
    except Exception:
        return empty
    if not values:
        return empty
    values.sort()

    def _pct(p: float) -> float:
        idx = min(len(values) - 1, max(0, int(round((p / 100.0) * (len(values) - 1)))))
        return values[idx]

    return {
        "count": float(len(values)),
        "p50": _pct(50),
        "p90": _pct(90),
        "p95": _pct(95),
        "p99": _pct(99),
        "max": values[-1],
    }


def snapshot(metrics: list[str] | None = None) -> dict[str, dict[str, float]]:
    names = metrics or [
        "webhook_ack_ms",
        "job_wait_ms",
        "ai_ms",
        "ai_luna_ms",
        "ai_tera_ms",
        "ai_luna_tera_gap_ms",
        "send_ms",
        "e2e_ms",
    ]
    return {name: percentiles(name) for name in names}
