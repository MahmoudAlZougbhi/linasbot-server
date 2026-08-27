"""Redis registry of worker replicas: heartbeat, health, restart bookkeeping."""

from __future__ import annotations

import json
import os
import time
from typing import Any

STATUSES = ("ready", "busy", "draining", "unhealthy", "dead", "starting")

_PREFIX = (os.getenv("LINAS_WORKER_REG_PREFIX") or "linas:wreg").strip() or "linas:wreg"
_TTL_SEC = max(8, int(os.getenv("LINAS_WORKER_REG_TTL_SEC") or "20"))
_TEST_CLIENT: Any | None = None


def set_registry_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def _k(*parts: str) -> str:
    return ":".join((_PREFIX, *parts))


def heartbeat(
    worker_id: str,
    *,
    status: str,
    node_id: str = "",
    pid: int = 0,
    inflight: int = 0,
    started_at: float = 0.0,
    restart_count: int = 0,
    last_exit: str = "",
) -> None:
    client = _client()
    if client is None:
        return
    now = time.time()
    payload = {
        "worker_id": worker_id,
        "status": status if status in STATUSES else "unhealthy",
        "node_id": node_id,
        "pid": int(pid or 0),
        "inflight": int(inflight),
        "started_at": float(started_at or now),
        "last_seen": now,
        "restart_count": int(restart_count),
        "last_exit": str(last_exit or "")[:200],
    }
    client.set(_k("worker", worker_id), json.dumps(payload, separators=(",", ":")), ex=_TTL_SEC)
    client.sadd(_k("live"), worker_id)
    client.expire(_k("live"), _TTL_SEC * 3)


def mark_dead(worker_id: str, *, last_exit: str = "") -> None:
    client = _client()
    if client is None:
        return
    raw = client.get(_k("worker", worker_id))
    data: dict[str, Any] = {}
    if raw:
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            data = {}
    data.update(
        {
            "worker_id": worker_id,
            "status": "dead",
            "last_seen": time.time(),
            "last_exit": str(last_exit or data.get("last_exit") or "dead")[:200],
        }
    )
    client.set(_k("worker", worker_id), json.dumps(data, separators=(",", ":")), ex=3600)
    client.srem(_k("live"), worker_id)


def list_workers() -> list[dict[str, Any]]:
    client = _client()
    if client is None:
        return []
    ids = [str(item) for item in (client.smembers(_k("live")) or [])]
    out: list[dict[str, Any]] = []
    stale: list[str] = []
    now = time.time()
    for worker_id in ids:
        raw = client.get(_k("worker", worker_id))
        if not raw:
            stale.append(worker_id)
            continue
        try:
            data = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            stale.append(worker_id)
            continue
        last_seen = float(data.get("last_seen") or 0.0)
        if now - last_seen > _TTL_SEC:
            data["status"] = "dead"
            stale.append(worker_id)
        out.append(data)
    for worker_id in stale:
        client.srem(_k("live"), worker_id)
    return out


def snapshot() -> dict[str, Any]:
    workers = list_workers()
    counts = {name: 0 for name in STATUSES}
    for item in workers:
        status = str(item.get("status") or "unhealthy")
        counts[status] = counts.get(status, 0) + 1
    healthy = counts["ready"] + counts["busy"] + counts["starting"]
    return {
        "workers": workers,
        "counts": counts,
        "healthy": healthy,
        "actual": len(workers),
    }
