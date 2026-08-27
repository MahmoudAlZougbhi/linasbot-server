"""Redis SoT for AI reply turn records (generation + delivery resume).

Local JSON files remain only when Redis is not required. When Redis is the
cross-node store, a failed write raises instead of silently using the file.
"""

from __future__ import annotations

import json
import os
from typing import Any

_PREFIX = (os.getenv("LINAS_TURN_PREFIX") or "linas:turn").strip() or "linas:turn"
_TTL_SEC = max(300, int(os.getenv("LINAS_TURN_TTL_SEC") or "604800"))
_TEST_CLIENT: Any | None = None


class TurnStoreUnavailable(RuntimeError):
    """Redis turn store is required but not reachable."""


def set_turn_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def store_enabled() -> bool:
    if _TEST_CLIENT is not None:
        return True
    from services.scale.message_combine_policy import distributed_combine_enabled

    return distributed_combine_enabled()


def store_required() -> bool:
    return store_enabled() and _TEST_CLIENT is None


def _k(*parts: str) -> str:
    return ":".join((_PREFIX, *parts))


def save_turn(data: dict[str, Any]) -> bool:
    client = _client()
    lid = str(data.get("logical_reply_id") or "").strip()
    if not lid:
        return False
    if client is None:
        if store_required():
            raise TurnStoreUnavailable("turn_store_redis_unavailable")
        return False
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    try:
        pipe = client.pipeline(True)
        pipe.set(_k("id", lid), payload, ex=_TTL_SEC)
        claim = str(data.get("claim_key_basis") or "").strip()
        if claim:
            pipe.set(_k("claim", claim), lid, ex=_TTL_SEC)
        event_id = str(data.get("inbound_event_id") or "").strip()
        if event_id:
            pipe.set(_k("event", event_id), lid, ex=_TTL_SEC)
        pipe.execute()
        return True
    except Exception as exc:
        if store_required():
            raise TurnStoreUnavailable("turn_store_redis_unavailable") from exc
        return False


def load_turn(logical_reply_id: str) -> dict[str, Any] | None:
    lid = (logical_reply_id or "").strip()
    if not lid:
        return None
    client = _client()
    if client is None:
        if store_required():
            raise TurnStoreUnavailable("turn_store_redis_unavailable")
        return None
    try:
        raw = client.get(_k("id", lid))
    except Exception as exc:
        if store_required():
            raise TurnStoreUnavailable("turn_store_redis_unavailable") from exc
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_turn_by_claim(claim_key_basis: str) -> dict[str, Any] | None:
    client = _client()
    claim = (claim_key_basis or "").strip()
    if not claim or client is None:
        return None
    try:
        lid = client.get(_k("claim", claim))
    except Exception:
        return None
    if not lid:
        return None
    return load_turn(str(lid))


def load_turn_by_event(inbound_event_id: str) -> dict[str, Any] | None:
    client = _client()
    event_id = (inbound_event_id or "").strip()
    if not event_id or client is None:
        return None
    try:
        lid = client.get(_k("event", event_id))
    except Exception:
        return None
    if not lid:
        return None
    return load_turn(str(lid))
