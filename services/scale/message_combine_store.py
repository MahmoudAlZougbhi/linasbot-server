"""Atomic Redis combine buffer: append, debounce generation, drain.

Pending chunks are a LIST (RPUSH). A SET prevents duplicate webhook replays
from appending the same platform event twice. Generation increments on every
new chunk so a stale sleeper can detect it was superseded.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_COMBINE_PREFIX") or "linas:combine").strip() or "linas:combine"
_TTL_SEC = max(60, int(os.getenv("LINAS_COMBINE_TTL_SEC") or "86400"))
_TEST_CLIENT: Any | None = None


def set_combine_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def _safe_user(user_key: str) -> str:
    return "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in user_key)[:200]


def _keys(user_key: str) -> tuple[str, str, str, str, str]:
    safe = _safe_user(user_key)
    return (
        f"{_PREFIX}:pending:{safe}",
        f"{_PREFIX}:seen:{safe}",
        f"{_PREFIX}:gen:{safe}",
        f"{_PREFIX}:due:{safe}",
        f"{_PREFIX}:ctx:{safe}",
    )


def combine_redis_available() -> bool:
    if _TEST_CLIENT is not None:
        return True
    from services.scale.message_combine_policy import distributed_combine_enabled

    if not distributed_combine_enabled():
        return False
    return _client() is not None


def append_chunk(
    user_key: str,
    *,
    text: str,
    event_id: str = "",
    mid: str = "",
    trace_id: str = "",
    delay_seconds: float = 3.0,
    now: float | None = None,
) -> dict[str, Any]:
    """Append one chunk. Duplicate event_id/mid is a no-op.

    Returns {accepted, generation, due_at, duplicate}.
    """
    client = _client()
    ts = time.time() if now is None else float(now)
    due_at = ts + max(0.0, float(delay_seconds))
    if _TEST_CLIENT is None:
        from services.scale.message_combine_policy import distributed_combine_enabled

        if not distributed_combine_enabled():
            return {"accepted": True, "generation": 0, "due_at": due_at, "duplicate": False, "redis": False}
    seen = (event_id or mid or "").strip() or f"anon:{ts}:{hash(text) & 0xFFFFFFFF:x}"
    chunk = {
        "text": str(text),
        "event_id": str(event_id or ""),
        "mid": str(mid or ""),
        "trace_id": str(trace_id or ""),
        "ts": ts,
    }
    if client is None:
        return {"accepted": True, "generation": 0, "due_at": due_at, "duplicate": False, "redis": False}
    pending, seen_key, gen_key, due_key, _ctx = _keys(user_key)
    try:
        added = int(client.sadd(seen_key, seen) or 0)
        client.expire(seen_key, _TTL_SEC)
        if added == 0:
            return {
                "accepted": False,
                "generation": int(client.get(gen_key) or 0),
                "due_at": current_due(user_key),
                "duplicate": True,
                "redis": True,
            }
        pipe = client.pipeline(True)
        pipe.rpush(pending, json.dumps(chunk, separators=(",", ":")))
        pipe.expire(pending, _TTL_SEC)
        pipe.incr(gen_key)
        pipe.expire(gen_key, _TTL_SEC)
        pipe.set(due_key, str(due_at), ex=_TTL_SEC)
        results = pipe.execute()
        generation = int(results[2] or 0)
    except Exception as exc:
        raise RuntimeError("combine_append_failed") from exc
    return {
        "accepted": True,
        "generation": generation,
        "due_at": due_at,
        "duplicate": False,
        "redis": True,
    }


def current_generation(user_key: str) -> int:
    client = _client()
    if client is None:
        return 0
    raw = client.get(_keys(user_key)[2])
    return int(raw or 0)


def current_due(user_key: str) -> float:
    client = _client()
    if client is None:
        return 0.0
    raw = client.get(_keys(user_key)[3])
    return float(raw or 0.0)


def generation_is_current(user_key: str, generation: int) -> bool:
    if generation <= 0:
        return True
    return current_generation(user_key) == int(generation)


def drain_if_due(user_key: str, *, now: float | None = None) -> list[dict[str, Any]] | None:
    """Return chunks when the quiet period elapsed; None if still waiting."""
    client = _client()
    ts = time.time() if now is None else float(now)
    if client is None:
        return []
    pending, _seen, _gen, due_key, _ctx = _keys(user_key)
    due = float(client.get(due_key) or 0)
    if due > ts:
        return None
    items = list(client.lrange(pending, 0, -1) or [])
    client.delete(pending)
    out: list[dict[str, Any]] = []
    for item in items or []:
        try:
            parsed = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            parsed = {"text": str(item)}
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def peek_pending(user_key: str) -> list[dict[str, Any]]:
    client = _client()
    if client is None:
        return []
    raw = client.lrange(_keys(user_key)[0], 0, -1)
    out: list[dict[str, Any]] = []
    for item in raw or []:
        try:
            parsed = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def save_context(user_key: str, context: dict[str, Any]) -> bool:
    client = _client()
    if client is None:
        return False
    try:
        safe = {
            str(k): v
            for k, v in context.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        client.set(_keys(user_key)[4], json.dumps(safe, separators=(",", ":")), ex=_TTL_SEC)
        return True
    except Exception:
        return False


def load_context(user_key: str) -> dict[str, Any]:
    client = _client()
    if client is None:
        return {}
    raw = client.get(_keys(user_key)[4])
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
