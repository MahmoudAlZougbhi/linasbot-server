"""Outbound delivery ledger: not_started → started → sent|failed|unknown.

Unknown means the provider call may have succeeded. Never treat unknown as a
normal failure and resend.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

_PREFIX = (os.getenv("LINAS_DELIVERY_PREFIX") or "linas:deliv").strip() or "linas:deliv"
_TTL_SEC = max(300, int(os.getenv("LINAS_DELIVERY_TTL_SEC") or "604800"))
_TEST_CLIENT: Any | None = None

STATES = ("not_started", "started", "unknown", "sent", "failed")


def set_delivery_redis_for_tests(client: Any | None) -> None:
    global _TEST_CLIENT
    _TEST_CLIENT = client


def _client() -> Any | None:
    if _TEST_CLIENT is not None:
        return _TEST_CLIENT
    from services.scale.redis_pool import redis_client

    return redis_client()


def _key(delivery_key: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in delivery_key)[:200]
    return f"{_PREFIX}:{safe}"


def _load(delivery_key: str) -> dict[str, Any]:
    client = _client()
    empty = {"key": delivery_key, "state": "not_started", "provider_message_id": "", "updated_at": 0.0}
    if client is None:
        return empty
    raw = client.get(_key(delivery_key))
    if not raw:
        return empty
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return empty
    return data if isinstance(data, dict) else empty


def _save(data: dict[str, Any]) -> None:
    client = _client()
    if client is None:
        return
    data["updated_at"] = time.time()
    client.set(_key(str(data["key"])), json.dumps(data, separators=(",", ":")), ex=_TTL_SEC)


def begin_send(delivery_key: str) -> str:
    """Return the action: send | skip_sent | skip_unknown."""
    data = _load(delivery_key)
    state = str(data.get("state") or "not_started")
    if state == "sent":
        return "skip_sent"
    if state in {"unknown", "started"}:
        return "skip_unknown"
    data["key"] = delivery_key
    data["state"] = "started"
    _save(data)
    return "send"


def confirm_sent(delivery_key: str, *, provider_message_id: str = "") -> None:
    data = _load(delivery_key)
    data["key"] = delivery_key
    data["state"] = "sent"
    if provider_message_id:
        data["provider_message_id"] = str(provider_message_id)
    _save(data)


def confirm_failed(delivery_key: str, *, retryable: bool = True) -> None:
    data = _load(delivery_key)
    if str(data.get("state") or "") == "sent":
        return
    data["key"] = delivery_key
    data["state"] = "failed" if retryable else "unknown"
    _save(data)


def mark_unknown(delivery_key: str) -> None:
    data = _load(delivery_key)
    if str(data.get("state") or "") == "sent":
        return
    data["key"] = delivery_key
    data["state"] = "unknown"
    _save(data)


def release_unknown_for_retry(delivery_key: str) -> bool:
    """Allow begin_send after a skip_unknown when Graph never stored a message id.

    Unknown normally forbids resend because the provider call may have succeeded.
    This release is only for the never-accepted case: no sent state and no id.
    """
    key = str(delivery_key or "").strip()
    if not key:
        return False
    data = _load(key)
    state = str(data.get("state") or "not_started")
    if state == "sent" or str(data.get("provider_message_id") or "").strip():
        return False
    if state not in {"unknown", "started"}:
        return False
    data["key"] = key
    data["state"] = "failed"
    _save(data)
    return True


def snapshot(delivery_key: str) -> dict[str, Any]:
    return _load(delivery_key)
