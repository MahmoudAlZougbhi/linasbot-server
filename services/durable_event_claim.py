"""
Durable event/outbound claim helpers for multi-instance safety.

Uses Firestore create-if-absent when available, otherwise a file lock under
LINASBOT_DATA_ROOT. Claims can be released on processing failure so providers
can safely retry.

Compatibility facade: file/Firestore internals live in sibling modules.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import time
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar

from services.durable_event_claim_file import (
    EventClaimHandle,
    _claims_dir,
    _file_claim_path,
    _file_complete,
    _file_release,
    _file_try_claim,
    _firestore_claim_document_id,
    _safe_claim_metadata,
    event_claim_handle_from_token,
    get_file_claim_status,
    is_stale_file_claim,
    local_event_claim_store_lock,
    meta_claim_binding_digest,
)
from services.durable_event_claim_firestore import (
    _firestore_owner_transition,
    _firestore_try_claim,
    _is_already_exists,
)
from storage.persistent_storage import LOGS_DIR, ensure_dirs

_T = TypeVar("_T")
_FACADE_REEXPORTS = (
    LOGS_DIR,
    _claims_dir,
    _safe_claim_metadata,
    ensure_dirs,
    is_stale_file_claim,
    meta_claim_binding_digest,
)


async def try_claim_event_handle(
    namespace: str,
    key: str,
    *,
    ttl_seconds: float = 300.0,
    firestore_collection: str | None = None,
    firestore_document_id: str | None = None,
    firestore_claim_metadata: dict[str, Any] | None = None,
    meta_binding_id: str = "",
) -> EventClaimHandle | None:
    """
    Return True if this worker owns the event and should process it.
    Fail-closed when neither Firestore nor file claim can be established.
    """
    original_boolean_api = globals().get("_ORIGINAL_TRY_CLAIM_EVENT")
    current_boolean_api = globals().get("try_claim_event")
    if original_boolean_api is not None and current_boolean_api is not original_boolean_api:
        # Unit tests deployed before the owner-capability API monkeypatch the
        # Boolean wrapper. Preserve that explicit test seam without weakening
        # the production implementation.
        claimed = await current_boolean_api(  # type: ignore[misc]
            namespace,
            key,
            ttl_seconds=ttl_seconds,
            firestore_collection=firestore_collection,
            firestore_document_id=firestore_document_id,
            firestore_claim_metadata=firestore_claim_metadata,
            meta_binding_id=meta_binding_id,
        )
        if not claimed:
            return None
        ns = (namespace or "default").strip() or "default"
        mid = (key or "").strip()
        token = secrets.token_urlsafe(32)
        return EventClaimHandle(
            namespace=ns,
            key=mid,
            collection=(firestore_collection or ns).strip(),
            document_id=_firestore_claim_document_id(ns, mid, document_id=firestore_document_id),
            owner_token=token,
            generation=1,
            nonproduction_bypass=True,
        )

    mid = (key or "").strip()
    if not mid:
        return None
    ns = (namespace or "default").strip() or "default"
    coll = (firestore_collection or ns).strip()
    owner_token = secrets.token_urlsafe(32)
    owner_hash = hashlib.sha256(f"event-claim-owner\0{owner_token}".encode()).hexdigest()

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
        doc_id = _firestore_claim_document_id(ns, mid, document_id=firestore_document_id)
        ref = db.collection("artifacts").document("linas-ai-bot-backend").collection(coll).document(doc_id)
        created_at_marker = server_timestamp

        try:
            generation = await asyncio.to_thread(
                _firestore_try_claim,
                db,
                ref=ref,
                namespace=ns,
                key=mid,
                ttl_seconds=ttl_seconds,
                metadata=dict(firestore_claim_metadata or {}),
                server_timestamp=created_at_marker,
                owner_hash=owner_hash,
                meta_binding_id=str(meta_binding_id or "").strip(),
            )
            if not generation:
                return None
            return event_claim_handle_from_token(
                ns,
                mid,
                firestore_collection=coll,
                owner_token=owner_token,
                generation=generation,
                firestore_document_id=firestore_document_id,
            )
        except Exception as e:
            if _is_already_exists(e):
                return None
            from config import is_production_runtime

            if is_production_runtime():
                print(f"⚠️ durable_event_claim shared claim failed closed: {type(e).__name__}")
                return None
            print(f"⚠️ durable_event_claim Firestore create failed; file fallback: {type(e).__name__}")

    if db is None:
        from config import is_production_runtime

        if is_production_runtime():
            return None

    generation = await asyncio.to_thread(
        _file_try_claim,
        ns,
        mid,
        ttl_seconds=ttl_seconds,
        owner_hash=owner_hash,
        metadata=firestore_claim_metadata,
        meta_binding_id=str(meta_binding_id or "").strip(),
    )
    if not generation:
        return None
    return event_claim_handle_from_token(
        ns,
        mid,
        firestore_collection=coll,
        owner_token=owner_token,
        generation=generation,
        firestore_document_id=firestore_document_id,
    )


async def try_claim_event(
    namespace: str,
    key: str,
    *,
    ttl_seconds: float = 300.0,
    firestore_collection: str | None = None,
    firestore_document_id: str | None = None,
    firestore_claim_metadata: dict[str, Any] | None = None,
    meta_binding_id: str = "",
) -> bool:
    """Backward-compatible Boolean claim API for one-shot dedupe callers."""

    return (
        await try_claim_event_handle(
            namespace,
            key,
            ttl_seconds=ttl_seconds,
            firestore_collection=firestore_collection,
            firestore_document_id=firestore_document_id,
            firestore_claim_metadata=firestore_claim_metadata,
            meta_binding_id=meta_binding_id,
        )
        is not None
    )


_ORIGINAL_TRY_CLAIM_EVENT = try_claim_event


def run_claim_coroutine_blocking(factory: Callable[[], Coroutine[Any, Any, _T]]) -> _T:
    """Run one claim coroutine from sync watchdog code, even inside an event loop."""

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="meta-claim-sync") as pool:
        return pool.submit(lambda: asyncio.run(factory())).result()


async def renew_event_claim(handle: EventClaimHandle, *, ttl_seconds: float) -> bool:
    """Extend only the exact live owner generation."""

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception:
        db = None
    if db is None:
        with local_event_claim_store_lock():
            data = get_file_claim_status(handle.namespace, handle.key) or {}
            if (
                str(data.get("status") or "") != "claimed"
                or str(data.get("owner_hash") or "") != handle.owner_hash
                or int(data.get("generation") or 0) != handle.generation
            ):
                return False
            data["expires_at_epoch"] = time.time() + max(1.0, float(ttl_seconds))
            path = _file_claim_path(handle.namespace, handle.key)
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
            try:
                fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(data, stream, separators=(",", ":"), sort_keys=True)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(tmp, path)
            finally:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
            return True
    ref = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection(handle.collection)
        .document(handle.document_id)
    )
    return await asyncio.to_thread(
        _firestore_owner_transition,
        db,
        ref=ref,
        handle=handle,
        action="renew",
        ttl_seconds=ttl_seconds,
    )


async def run_under_event_claim(
    handle: EventClaimHandle,
    *,
    ttl_seconds: float,
    operation: Callable[[], Coroutine[Any, Any, _T]],
) -> _T:
    """Renew a claim while work runs and cancel immediately if ownership is lost."""

    if handle.nonproduction_bypass:
        return await operation()
    if not await renew_event_claim(handle, ttl_seconds=ttl_seconds):
        raise RuntimeError("event claim ownership changed")
    task = asyncio.create_task(operation())

    async def _heartbeat() -> None:
        interval = max(1.0, min(30.0, float(ttl_seconds) / 3.0))
        while not task.done():
            await asyncio.sleep(interval)
            if task.done():
                return
            try:
                owned = await renew_event_claim(handle, ttl_seconds=ttl_seconds)
            except BaseException:
                owned = False
            if not owned:
                task.cancel()
                return

    heartbeat = asyncio.create_task(_heartbeat())
    try:
        return await task
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


async def release_event_claim(
    namespace: str,
    key: str,
    *,
    firestore_collection: str | None = None,
    firestore_document_id: str | None = None,
    claim_handle: EventClaimHandle | None = None,
) -> None:
    """Release a claim so a retry can reprocess after failure."""
    mid = (key or "").strip()
    if not mid:
        return
    ns = (namespace or "default").strip() or "default"
    coll = (firestore_collection or ns).strip()
    await asyncio.to_thread(
        _file_release,
        ns,
        mid,
        owner_hash=claim_handle.owner_hash if claim_handle else None,
    )

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception:
        db = None
    if not db:
        return
    doc_id = _firestore_claim_document_id(ns, mid, document_id=firestore_document_id)
    ref = db.collection("artifacts").document("linas-ai-bot-backend").collection(coll).document(doc_id)
    if claim_handle is None:
        from config import is_production_runtime

        if is_production_runtime():
            raise RuntimeError("claim owner is required for production release")
        try:
            await asyncio.to_thread(ref.delete)
        except Exception as e:
            print(f"⚠️ durable_event_claim release failed: {type(e).__name__}")
        return
    try:
        await asyncio.to_thread(
            _firestore_owner_transition,
            db,
            ref=ref,
            handle=claim_handle,
            action="release",
            server_timestamp=None,
        )
    except Exception as e:
        print(f"⚠️ durable_event_claim release failed: {type(e).__name__}")


async def complete_event_claim(
    namespace: str,
    key: str,
    *,
    firestore_collection: str | None = None,
    firestore_document_id: str | None = None,
    claim_handle: EventClaimHandle | None = None,
) -> None:
    mid = (key or "").strip()
    if not mid:
        return
    ns = (namespace or "default").strip() or "default"
    await asyncio.to_thread(
        _file_complete,
        ns,
        mid,
        owner_hash=claim_handle.owner_hash if claim_handle else None,
    )
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
    doc_id = _firestore_claim_document_id(ns, mid, document_id=firestore_document_id)
    ref = db.collection("artifacts").document("linas-ai-bot-backend").collection(coll).document(doc_id)
    if claim_handle is None:
        from config import is_production_runtime

        if is_production_runtime():
            raise RuntimeError("claim owner is required for production completion")
        try:
            await asyncio.to_thread(
                ref.set,
                {"status": "completed", "completed_at": firestore.SERVER_TIMESTAMP},
                merge=True,
            )
        except Exception:
            pass
        return
    try:
        await asyncio.to_thread(
            _firestore_owner_transition,
            db,
            ref=ref,
            handle=claim_handle,
            action="complete",
            server_timestamp=firestore.SERVER_TIMESTAMP,
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
    return bool(
        _file_try_claim(
            "scheduler_jobs",
            jid,
            ttl_seconds=ttl_seconds,
            owner_hash=hashlib.sha256(f"scheduler\0{os.getpid()}".encode()).hexdigest(),
        )
    )


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
