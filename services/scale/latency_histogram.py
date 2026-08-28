"""Shared Redis latency histograms with percentile reads (p50/p90/p95/p99/max)."""

from __future__ import annotations

import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_HIST_PREFIX") or "linas:hist").strip() or "linas:hist"
_TTL_SEC = max(60, int(os.getenv("LINAS_HIST_TTL_SEC") or "3600"))
_MAX_SAMPLES = max(100, int(os.getenv("LINAS_HIST_MAX_SAMPLES") or "4000"))
_WINDOW_SEC = max(15, int(os.getenv("LINAS_HIST_WINDOW_SEC") or "90"))
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
    member = f"{ts:.6f}:{float(value_ms):.3f}:{os.getpid()}:{id(value_ms) % 100000}"
    key = f"{_PREFIX}:{name}"
    try:
        pipe = client.pipeline()
        pipe.zadd(key, {member: ts})
        pipe.zremrangebyscore(key, 0, ts - float(_WINDOW_SEC))
        pipe.zremrangebyrank(key, 0, -(_MAX_SAMPLES + 1))
        pipe.expire(key, max(_TTL_SEC, _WINDOW_SEC * 2))
        pipe.execute()
    except Exception:
        return


def _value_from_member(member: Any) -> float | None:
    text = str(member or "")
    parts = text.split(":")
    if len(parts) < 2:
        return None
    try:
        return float(parts[1])
    except ValueError:
        return None


def percentiles(metric: str, *, now: float | None = None) -> dict[str, float]:
    name = "".join(c if c.isalnum() or c in "_:-" else "_" for c in metric)[:80]
    client = _client()
    empty = {"count": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0}
    if client is None:
        return empty
    ts = time.time() if now is None else float(now)
    try:
        members = client.zrangebyscore(f"{_PREFIX}:{name}", ts - float(_WINDOW_SEC), ts) or []
        values = [item for item in (_value_from_member(member) for member in members) if item is not None]
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
