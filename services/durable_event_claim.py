"""
Durable event/outbound claim helpers for multi-instance safety.

Uses Firestore create-if-absent when available, otherwise a file lock under
LINASBOT_DATA_ROOT. Claims can be released on processing failure so providers
can safely retry.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from storage.persistent_storage import LOGS_DIR, ensure_dirs


def _claims_dir() -> Path:
    ensure_dirs()
    d = Path(LOGS_DIR) / "durable_claims"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _is_already_exists(exc: BaseException) -> bool:
    if type(exc).__name__ in ("AlreadyExists", "Conflict"):
        return True
    code = getattr(exc, "code", None)
    if code in (409, "ALREADY_EXISTS"):
        return True
    s = str(exc).lower()
    return "already exists" in s or "already_exists" in s


def _file_claim_path(namespace: str, key: str) -> Path:
    digest = hashlib.sha256(f"{namespace}\0{key}".encode()).hexdigest()
    return _claims_dir() / namespace / f"{digest}.json"


def _file_try_claim(namespace: str, key: str, *, ttl_seconds: float) -> bool:
    path = _file_claim_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            created = float(data.get("created_at") or 0)
            status = str(data.get("status") or "claimed")
            if status == "completed" and now - created < ttl_seconds:
                return False
            if status == "claimed" and now - created < ttl_seconds:
                return False
            # Expired or released — allow reclaim
        except Exception:
            pass
    tmp = path.with_suffix(".tmp")
    payload: dict[str, Any] = {
        "namespace": namespace,
        "key_prefix": (key or "")[:200],
        "created_at": now,
        "status": "claimed",
        "pid": os.getpid(),
    }
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
        os.replace(str(tmp), str(path))
        return True
    except FileExistsError:
        # Another writer; treat as contended
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False
    except Exception:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        return False


def _file_release(namespace: str, key: str) -> None:
    path = _file_claim_path(namespace, key)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _file_complete(namespace: str, key: str) -> None:
    path = _file_claim_path(namespace, key)
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = "completed"
        data["completed_at"] = time.time()
        path.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


async def try_claim_event(
    namespace: str,
    key: str,
    *,
    ttl_seconds: float = 300.0,
    firestore_collection: str | None = None,
) -> bool:
    """
    Return True if this worker owns the event and should process it.
    Fail-closed when neither Firestore nor file claim can be established.
    """
    mid = (key or "").strip()
    if not mid:
        return False
    ns = (namespace or "default").strip() or "default"
    coll = (firestore_collection or ns).strip()

    # Capture SERVER_TIMESTAMP in the import scope so the except path never needs
    # an unbound/None module assignment (avoids type: ignore on failed imports).
    server_timestamp: object | None = None
    db = None
    try:
        from google.cloud import firestore

        from utils.utils import get_firestore_db

        db = get_firestore_db()
        server_timestamp = firestore.SERVER_TIMESTAMP
    except Exception:
        db = None
        server_timestamp = None

    if db is not None and server_timestamp is not None:
        doc_id = hashlib.sha256(f"{ns}\0{mid}".encode()).hexdigest()
        ref = db.collection("artifacts").document("linas-ai-bot-backend").collection(coll).document(doc_id)
        created_at_marker = server_timestamp

        def _create() -> None:
            ref.create(
                {
                    "created_at": created_at_marker,
                    "namespace": ns[:64],
                    "key_prefix": mid[:200],
                    "status": "claimed",
                }
            )

        try:
            await asyncio.to_thread(_create)
            return True
        except Exception as e:
            if _is_already_exists(e):
                return False
            # Firestore error — durable file fallback (fail-closed if file also fails)
            print(f"⚠️ durable_event_claim Firestore create failed; file fallback: {e}")

    claimed = await asyncio.to_thread(_file_try_claim, ns, mid, ttl_seconds=ttl_seconds)
    return claimed


async def release_event_claim(
    namespace: str,
    key: str,
    *,
    firestore_collection: str | None = None,
) -> None:
    """Release a claim so a retry can reprocess after failure."""
    mid = (key or "").strip()
    if not mid:
        return
    ns = (namespace or "default").strip() or "default"
    coll = (firestore_collection or ns).strip()
    await asyncio.to_thread(_file_release, ns, mid)

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception:
        db = None
    if not db:
        return
    doc_id = hashlib.sha256(f"{ns}\0{mid}".encode()).hexdigest()
    ref = db.collection("artifacts").document("linas-ai-bot-backend").collection(coll).document(doc_id)
    try:
        await asyncio.to_thread(ref.delete)
    except Exception as e:
        print(f"⚠️ durable_event_claim release failed: {e}")


async def complete_event_claim(
    namespace: str,
    key: str,
    *,
    firestore_collection: str | None = None,
) -> None:
    mid = (key or "").strip()
    if not mid:
        return
    ns = (namespace or "default").strip() or "default"
    await asyncio.to_thread(_file_complete, ns, mid)
    # Firestore create already proves ownership; leave doc as completed marker.
    try:
        from google.cloud import firestore

        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception:
        return
    if not db:
        return
    coll = (firestore_collection or ns).strip()
    doc_id = hashlib.sha256(f"{ns}\0{mid}".encode()).hexdigest()
    ref = db.collection("artifacts").document("linas-ai-bot-backend").collection(coll).document(doc_id)
    try:
        await asyncio.to_thread(
            ref.set,
            {"status": "completed", "completed_at": firestore.SERVER_TIMESTAMP},
            merge=True,
        )
    except Exception:
        pass


def try_acquire_job_lock(job_id: str, *, ttl_seconds: float = 120.0) -> bool:
    """Distributed scheduler lock: Redis when available, else durable file claim."""
    jid = (job_id or "").strip()
    if not jid:
        return False
    try:
        from services.scale.redis_claims import redis_claims_fail_closed, redis_try_claim

        shared = redis_try_claim("scheduler_jobs", jid, ttl_seconds=float(ttl_seconds))
        if shared is not None:
            return bool(shared)
        if redis_claims_fail_closed():
            return False
    except Exception:
        from services.scale.redis_claims import redis_claims_fail_closed

        if redis_claims_fail_closed():
            return False
    return _file_try_claim("scheduler_jobs", jid, ttl_seconds=ttl_seconds)


def release_job_lock(job_id: str) -> None:
    jid = (job_id or "").strip()
    if not jid:
        return
    try:
        import redis as redis_lib

        from services.queues.config import redis_url

        url = redis_url()
        if url:
            client = redis_lib.Redis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1.5,
                socket_timeout=1.5,
            )
            prefix = (os.getenv("LINAS_CLAIM_PREFIX") or "linas:claim").strip()
            safe = "".join(c if c.isalnum() or c in "-_.:/" else "_" for c in jid)[:200]
            client.delete(f"{prefix}:scheduler_jobs:{safe}")
    except Exception:
        pass
    _file_release("scheduler_jobs", jid)
