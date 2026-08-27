"""End-to-end trace stages stored in Redis (webhook → queue → worker → AI → send)."""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

_PREFIX = (os.getenv("LINAS_TRACE_PREFIX") or "linas:trace").strip() or "linas:trace"
_TTL_SEC = max(300, int(os.getenv("LINAS_TRACE_TTL_SEC") or "86400"))
_TEST_CLIENT: Any | None = None

STAGES = (
    "webhook_received",
    "webhook_acked",
    "queued",
    "worker_started",
    "ai_started",
    "ai_luna_started",
    "ai_luna_finished",
    "ai_tera_started",
    "ai_tera_finished",
    "ai_finished",
    "send_started",
    "send_ok",
)


def set_trace_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def new_trace_id() -> str:
    return "tr_" + uuid.uuid4().hex


def mark(trace_id: str, stage: str, *, ts: float | None = None) -> None:
    tid = (trace_id or "").strip()
    if not tid or stage not in STAGES:
        return
    client = _client()
    if client is None:
        return
    at = time.time() if ts is None else float(ts)
    key = f"{_PREFIX}:{tid}"
    try:
        client.hset(key, stage, f"{at:.6f}")
        client.expire(key, _TTL_SEC)
    except Exception:
        return


def snapshot(trace_id: str) -> dict[str, Any]:
    tid = (trace_id or "").strip()
    if not tid:
        return {}
    client = _client()
    if client is None:
        return {"trace_id": tid, "stages": {}, "durations_ms": {}}
    raw = client.hgetall(f"{_PREFIX}:{tid}") or {}
    stages: dict[str, float] = {}
    for name, value in raw.items():
        try:
            stages[str(name)] = float(value)
        except (TypeError, ValueError):
            continue
    durations: dict[str, float] = {}
    pairs = (
        ("ack_ms", "webhook_received", "webhook_acked"),
        ("queue_wait_ms", "queued", "worker_started"),
        ("ai_ms", "ai_started", "ai_finished"),
        ("luna_ms", "ai_luna_started", "ai_luna_finished"),
        ("tera_ms", "ai_tera_started", "ai_tera_finished"),
        ("luna_tera_gap_ms", "ai_luna_finished", "ai_tera_started"),
        ("post_ai_ms", "ai_finished", "send_started"),
        ("send_ms", "send_started", "send_ok"),
        ("e2e_ms", "webhook_received", "send_ok"),
    )
    for label, start, end in pairs:
        if start in stages and end in stages:
            durations[label] = max(0.0, (stages[end] - stages[start]) * 1000.0)
    return {"trace_id": tid, "stages": stages, "durations_ms": durations}
