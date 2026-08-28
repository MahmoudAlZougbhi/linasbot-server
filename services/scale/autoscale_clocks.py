"""Redis clocks for quiet scale-down and node-layer pressure. No cloud calls."""

from __future__ import annotations

import json
import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_SCALE_CTRL_PREFIX") or "linas:scale").strip() or "linas:scale"
_TEST_CLIENT: Any | None = None


def set_clocks_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def _k(*parts: str) -> str:
    return ":".join((_PREFIX, *parts))


def _since(key: str, *, active: bool, now: float) -> float:
    client = _client()
    if client is None:
        return 0.0
    if not active:
        try:
            client.delete(key)
        except Exception:
            pass
        return 0.0
    raw = client.get(key)
    try:
        started = float(raw or 0.0)
    except (TypeError, ValueError):
        started = 0.0
    if started <= 0:
        client.set(key, f"{now:.6f}")
        return 0.0
    return max(0.0, now - started)


def pressure_seconds(*, active: bool, now: float | None = None) -> float:
    ts = time.time() if now is None else float(now)
    return _since(_k("node_pressure_since"), active=active, now=ts)


def quiet_seconds(*, quiet: bool, now: float | None = None) -> float:
    ts = time.time() if now is None else float(now)
    return _since(_k("quiet_since"), active=quiet, now=ts)


def extra_quiet_ready(quiet_sec: float) -> bool:
    raw = (os.getenv("LINAS_AUTOSCALE_EXTRA_QUIET_SEC") or "120").strip()
    try:
        threshold = max(30.0, float(raw))
    except ValueError:
        threshold = 120.0
    return float(quiet_sec) >= threshold


def node_attempt_cooled(*, now: float | None = None) -> bool:
    ts = time.time() if now is None else float(now)
    client = _client()
    if client is None:
        return False
    raw = client.get(_k("node_attempt_at"))
    try:
        last = float(raw or 0.0)
    except (TypeError, ValueError):
        last = 0.0
    if last <= 0:
        return True
    cooldown = float(os.getenv("LINAS_NODE_SCALE_ATTEMPT_COOLDOWN_SEC") or "300")
    return ts - last >= max(60.0, cooldown)


def mark_node_attempt(*, now: float | None = None) -> None:
    ts = time.time() if now is None else float(now)
    client = _client()
    if client is None:
        return
    client.set(_k("node_attempt_at"), f"{ts:.6f}")


def store_node_need(payload: dict[str, Any]) -> None:
    client = _client()
    if client is None:
        return
    client.set(_k("node_need"), json.dumps(payload, separators=(",", ":")), ex=24 * 3600)
