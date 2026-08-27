"""Structured dead-letter records. Replay remains delivery-only."""

from __future__ import annotations

import json
import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_DLQ_RECORD_PREFIX") or "linas:dlqrec").strip() or "linas:dlqrec"
_TTL_SEC = max(3600, int(os.getenv("LINAS_DLQ_RECORD_TTL_SEC") or str(14 * 24 * 3600)))
_INDEX = f"{_PREFIX}:index"
_TEST_CLIENT: Any | None = None

TRANSIENT_MARKERS = (
    "timeout",
    "429",
    "503",
    "500",
    "connection",
    "throttle",
    "retryable",
    "temporarily",
)


def set_dlq_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def classify_error(error: str) -> str:
    text = (error or "").lower()
    if any(marker in text for marker in TRANSIENT_MARKERS):
        return "transient"
    if "permanent" in text or "unknown_job_type" in text:
        return "permanent"
    return "unknown"


def record_dead(
    *,
    job_id: str,
    job_type: str,
    tenant_id: str,
    error: str,
    attempts: int,
    conversation_key: str = "",
    channel: str = "",
    created_at: float = 0.0,
    attempt_times: list[float] | None = None,
) -> dict[str, Any]:
    kind = classify_error(error)
    payload = {
        "job_id": job_id,
        "job_type": job_type,
        "tenant_id": tenant_id,
        "channel": channel,
        "conversation_key": conversation_key,
        "last_error": (error or "")[:500],
        "attempts": int(attempts),
        "created_at": float(created_at or time.time()),
        "dead_at": time.time(),
        "attempt_times": [float(x) for x in (attempt_times or [])][-12:],
        "error_kind": kind,
        "replay_mode": "delivery_only",
    }
    client = _client()
    if client is None:
        return payload
    key = f"{_PREFIX}:{job_id}"
    try:
        pipe = client.pipeline()
        pipe.set(key, json.dumps(payload, separators=(",", ":")), ex=_TTL_SEC)
        pipe.lpush(_INDEX, job_id)
        pipe.ltrim(_INDEX, 0, 1999)
        pipe.expire(_INDEX, _TTL_SEC)
        pipe.execute()
    except Exception:
        pass
    return payload


def get_record(job_id: str) -> dict[str, Any] | None:
    client = _client()
    if client is None:
        return None
    raw = client.get(f"{_PREFIX}:{job_id}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def recent(limit: int = 50) -> list[dict[str, Any]]:
    client = _client()
    if client is None:
        return []
    ids = client.lrange(_INDEX, 0, max(0, int(limit) - 1)) or []
    out: list[dict[str, Any]] = []
    for job_id in ids:
        rec = get_record(str(job_id))
        if rec:
            out.append(rec)
    return out
