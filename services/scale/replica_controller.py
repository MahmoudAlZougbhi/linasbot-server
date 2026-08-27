"""Apply autoscale decisions to Redis desired-replica keys (isolated/staging).

Does not call DigitalOcean. A supervisor (IsolatedReplicaPool or systemd)
reads desired counts and starts/stops processes with drain-before-stop.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from services.scale.autoscale_signal import ScaleRecommendation, recommend

_PREFIX = (os.getenv("LINAS_SCALE_CTRL_PREFIX") or "linas:scale").strip() or "linas:scale"
_TEST_CLIENT: Any | None = None


def set_controller_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def apply_enabled() -> bool:
    return (os.getenv("LINAS_AUTOSCALE_APPLY") or "").strip().lower() in {"1", "true", "yes", "on"}


def _k(*parts: str) -> str:
    return ":".join((_PREFIX, *parts))


@dataclass
class ReplicaState:
    api: int
    workers: int
    draining_workers: list[str]
    cooldown_until: float
    last_action: str
    last_action_at: float


def current_replicas(*, default_api: int = 2, default_workers: int = 16) -> ReplicaState:
    client = _client()
    if client is None:
        return ReplicaState(
            api=default_api,
            workers=default_workers,
            draining_workers=[],
            cooldown_until=0.0,
            last_action="none",
            last_action_at=0.0,
        )
    api = int(client.get(_k("desired", "api")) or default_api)
    workers = int(client.get(_k("desired", "workers")) or default_workers)
    draining = [str(item) for item in (client.smembers(_k("draining", "workers")) or [])]
    cooldown_until = float(client.get(_k("cooldown_until")) or 0.0)
    last_action = str(client.get(_k("last_action")) or "none")
    last_action_at = float(client.get(_k("last_action_at")) or 0.0)
    return ReplicaState(
        api=api,
        workers=workers,
        draining_workers=draining,
        cooldown_until=cooldown_until,
        last_action=last_action,
        last_action_at=last_action_at,
    )


def record_event(event: dict[str, Any]) -> None:
    client = _client()
    if client is None:
        return
    payload = json.dumps(event, separators=(",", ":"))
    key = _k("events")
    client.lpush(key, payload)
    client.ltrim(key, 0, 199)
    client.expire(key, 7 * 24 * 3600)


def recent_events(limit: int = 50) -> list[dict[str, Any]]:
    client = _client()
    if client is None:
        return []
    raw = client.lrange(_k("events"), 0, max(0, limit - 1)) or []
    out: list[dict[str, Any]] = []
    for item in raw:
        try:
            parsed = json.loads(item)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(parsed, dict):
            out.append(parsed)
    return out


def _write_desired(*, api: int, workers: int, action: str, now: float, cooldown_seconds: float) -> None:
    client = _client()
    if client is None:
        return
    pipe = client.pipeline()
    pipe.set(_k("desired", "api"), str(api))
    pipe.set(_k("desired", "workers"), str(workers))
    pipe.set(_k("last_action"), action)
    pipe.set(_k("last_action_at"), f"{now:.6f}")
    if cooldown_seconds > 0:
        pipe.set(_k("cooldown_until"), f"{now + cooldown_seconds:.6f}")
    pipe.execute()


def mark_worker_draining(worker_id: str, *, draining: bool) -> None:
    client = _client()
    if client is None:
        return
    key = _k("draining", "workers")
    if draining:
        client.sadd(key, worker_id)
    else:
        client.srem(key, worker_id)
    client.expire(key, 3600)


def worker_is_draining(worker_id: str) -> bool:
    client = _client()
    if client is None:
        return False
    return bool(client.sismember(_k("draining", "workers"), worker_id))


def maybe_apply(rec: ScaleRecommendation, *, detected_at: float | None = None) -> dict[str, Any]:
    """Write desired replica counts when LINAS_AUTOSCALE_APPLY is on."""
    now = time.time() if detected_at is None else float(detected_at)
    decided_at = time.time()
    state = current_replicas()
    cooldown_ok = now >= state.cooldown_until
    payload = {
        "detected_at": now,
        "decided_at": decided_at,
        "action": rec.action,
        "from_api": state.api,
        "from_workers": state.workers,
        "to_api": rec.api_replicas,
        "to_workers": rec.worker_replicas,
        "reason": rec.reason,
        "applied": False,
        "apply_enabled": apply_enabled(),
    }
    if not apply_enabled():
        record_event(payload)
        return payload
    if rec.action == "hold":
        record_event(payload)
        return payload
    if rec.action == "scale_down" and not cooldown_ok:
        payload["action"] = "hold"
        payload["reason"] = "cooldown_hold"
        record_event(payload)
        return payload
    up_cd = float(os.getenv("LINAS_AUTOSCALE_UP_COOLDOWN_SEC") or "8")
    down_cd = float(os.getenv("LINAS_AUTOSCALE_DOWN_COOLDOWN_SEC") or "60")
    cooldown = up_cd if rec.action.startswith("scale_up") else down_cd
    _write_desired(
        api=rec.api_replicas,
        workers=rec.worker_replicas,
        action=rec.action,
        now=now,
        cooldown_seconds=cooldown,
    )
    payload["applied"] = True
    payload["provision_started_at"] = time.time()
    record_event(payload)
    return payload


def tick(**recommend_kwargs: Any) -> dict[str, Any]:
    rec = recommend(**recommend_kwargs)
    applied = maybe_apply(rec)
    return {"recommendation": asdict(rec), "apply": applied, "state": asdict(current_replicas())}
