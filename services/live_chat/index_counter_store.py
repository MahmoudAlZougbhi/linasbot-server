"""One inbox-counter document per tenant, shared by both API nodes.

Opening the inbox reads that document. Redis keeps the copy for 25 seconds so
the peer node does not read it again. A missing document is built once by
paging the tenant index. Later state changes adjust the same document.
"""

from __future__ import annotations

import json
from typing import Any

from services.scale.firestore_usage import record_usage

_KEYS = ("all", "waiting", "with_operator", "bot_active", "closed")
_PAGE = 80
_CACHE_SECONDS = 25
_APP = "linas-ai-bot-backend"


def empty_counters() -> dict[str, int]:
    return {key: 0 for key in _KEYS}


def bucket_for_state(state: str) -> str:
    value = (state or "").strip()
    if value == "waiting_for_operator":
        return "waiting"
    if value == "assigned_to_operator":
        return "with_operator"
    if value in {"resolved", "archived"}:
        return "closed"
    return "bot_active"


def _counter_collection(db: Any) -> Any:
    return db.collection("artifacts").document(_APP).collection("live_chat_index_counters")


def _index_collection(db: Any) -> Any:
    return db.collection("artifacts").document(_APP).collection("live_chat_index")


def _redis() -> Any | None:
    try:
        from services.queues.config import redis_url

        url = redis_url()
        if not url:
            return None
        import redis

        client = redis.Redis.from_url(url, decode_responses=True, socket_connect_timeout=0.4, socket_timeout=0.4)
        client.ping()
        return client
    except Exception:
        return None


def _cache_key(tenant_id: str) -> str:
    return f"linas:claim:inbox_counters:{tenant_id}"


def _cache_get(tenant_id: str) -> dict[str, int] | None:
    client = _redis()
    if client is None:
        return None
    try:
        raw = client.get(_cache_key(tenant_id))
    except Exception:
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return {key: int(payload.get(key) or 0) for key in _KEYS}


def _cache_set(tenant_id: str, counters: dict[str, int]) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.set(_cache_key(tenant_id), json.dumps(counters), ex=_CACHE_SECONDS)
    except Exception:
        return


def _cache_drop(tenant_id: str) -> None:
    client = _redis()
    if client is None:
        return
    try:
        client.delete(_cache_key(tenant_id))
    except Exception:
        return


def _ready_counters(snapshot: Any) -> dict[str, int] | None:
    if getattr(snapshot, "exists", False) is not True:
        return None
    data = snapshot.to_dict() or {}
    if data.get("ready") is not True:
        return None
    return {key: int(data.get(key) or 0) for key in _KEYS}


def read_durable_counters(db: Any, tenant_id: str) -> dict[str, int] | None:
    snapshot = _counter_collection(db).document(tenant_id).get(timeout=4, retry=None)
    record_usage("inbox_counter", reads=1)
    return _ready_counters(snapshot)


def apply_counter_delta(db: Any, tenant_id: str, previous_state: str, next_state: str) -> None:
    """Adjust the shared document after an index row changes state."""
    previous = (previous_state or "").strip()
    nxt = (next_state or "").strip()
    if not tenant_id or previous == nxt:
        return
    if previous and nxt and bucket_for_state(previous) == bucket_for_state(nxt):
        return
    ref = _counter_collection(db).document(tenant_id)
    snapshot = ref.get(timeout=4, retry=None)
    record_usage("inbox_counter_delta", reads=1)
    if _ready_counters(snapshot) is None:
        return
    from google.cloud.firestore_v1.transforms import Increment

    updates: dict[str, Any] = {}
    if previous:
        updates[bucket_for_state(previous)] = Increment(-1)
    if nxt:
        updates[bucket_for_state(nxt)] = Increment(1)
    all_delta = (1 if nxt else 0) - (1 if previous else 0)
    if all_delta:
        updates["all"] = Increment(all_delta)
    if not updates:
        return
    ref.update(updates)
    record_usage("inbox_counter_delta", writes=1)
    _cache_drop(tenant_id)


def rebuild_counters(db: Any, tenant_id: str, normalize: Any) -> dict[str, int]:
    """Page the tenant index and store the totals. A 5,000-document pass resumes later."""
    from google.cloud import firestore

    ref = _counter_collection(db).document(tenant_id)
    snapshot = ref.get(timeout=4, retry=None)
    record_usage("inbox_counter_rebuild", reads=1)
    prior = snapshot.to_dict() if getattr(snapshot, "exists", False) else {}
    resume = str((prior or {}).get("resume") or "").strip()
    totals = {key: int((prior or {}).get(key) or 0) for key in _KEYS} if resume else empty_counters()
    scanned = int((prior or {}).get("scanned") or 0) if resume else 0
    query = (
        _index_collection(db)
        .where("tenant_id", "==", tenant_id)
        .order_by("last_message_at", direction=firestore.Query.DESCENDING)
    )
    added = 0
    last: Any = None
    last_stamp = resume
    finished = True
    while added < 5000:
        page = query.limit(_PAGE)
        if last is not None:
            page = page.start_after(last)
        elif resume:
            page = page.start_after([resume])
        docs = list(page.stream(timeout=8, retry=None))
        record_usage("inbox_counter_rebuild", reads=max(1, len(docs)))
        if not docs:
            finished = True
            break
        for doc in docs:
            data = doc.to_dict() or {}
            state = str(normalize(data) or "")
            totals["all"] += 1
            totals[bucket_for_state(state)] += 1
        scanned += len(docs)
        added += len(docs)
        last = docs[-1]
        stamp = (last.to_dict() or {}).get("last_message_at") or ""
        if hasattr(stamp, "isoformat"):
            stamp = stamp.isoformat()
        last_stamp = str(stamp)
        if len(docs) < _PAGE:
            finished = True
            break
        finished = False
    body = {**totals, "ready": finished, "scanned": scanned, "resume": "" if finished else last_stamp}
    ref.set(body)
    record_usage("inbox_counter_rebuild", writes=1)
    if finished:
        _cache_set(tenant_id, totals)
    return totals


def counters_for_tenant(db: Any, tenant_id: str, normalize: Any) -> dict[str, int]:
    cached = _cache_get(tenant_id)
    if cached is not None:
        return cached
    durable = read_durable_counters(db, tenant_id)
    if durable is not None:
        _cache_set(tenant_id, durable)
        return durable
    from services.scale.job_interval_lock import job_interval_lock

    with job_interval_lock(f"live_chat_counter_rebuild:{tenant_id}", ttl_seconds=60) as acquired:
        if not acquired:
            again = read_durable_counters(db, tenant_id)
            return again if again is not None else empty_counters()
        return rebuild_counters(db, tenant_id, normalize)
