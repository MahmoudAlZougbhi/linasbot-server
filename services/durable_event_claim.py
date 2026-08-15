"""
Durable event/outbound claim helpers for multi-instance safety.

Uses Firestore create-if-absent when available, otherwise a file lock under
LINASBOT_DATA_ROOT. Claims can be released on processing failure so providers
can safely retry.
"""

from __future__ import annotations

import asyncio
import fcntl
import hashlib
import json
import os
import secrets
import threading
import time
from collections.abc import Callable, Coroutine, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from storage.persistent_storage import LOGS_DIR, ensure_dirs

_T = TypeVar("_T")
_LOCAL_CLAIM_THREAD_LOCK = threading.RLock()
_LOCAL_CLAIM_LOCK_STATE = threading.local()


@dataclass(frozen=True)
class EventClaimHandle:
    """Unforgeable owner capability for one claim generation."""

    namespace: str
    key: str
    collection: str
    document_id: str
    owner_token: str = field(repr=False)
    generation: int = 1
    nonproduction_bypass: bool = False

    @property
    def owner_hash(self) -> str:
        return hashlib.sha256(f"event-claim-owner\0{self.owner_token}".encode()).hexdigest()


def event_claim_handle_from_token(
    namespace: str,
    key: str,
    *,
    firestore_collection: str,
    owner_token: str,
    generation: int = 1,
    firestore_document_id: str | None = None,
) -> EventClaimHandle:
    token = str(owner_token or "").strip()
    if not 32 <= len(token) <= 128:
        raise ValueError("event claim owner token is invalid")
    ns = (namespace or "default").strip() or "default"
    mid = (key or "").strip()
    if not mid:
        raise ValueError("event claim key is invalid")
    collection = (firestore_collection or ns).strip()
    return EventClaimHandle(
        namespace=ns,
        key=mid,
        collection=collection,
        document_id=_firestore_claim_document_id(ns, mid, document_id=firestore_document_id),
        owner_token=token,
        generation=max(1, int(generation)),
    )


def _claims_dir() -> Path:
    ensure_dirs()
    d = Path(LOGS_DIR) / "durable_claims"
    d.mkdir(parents=True, exist_ok=True)
    return d


@contextmanager
def local_event_claim_store_lock() -> Iterator[None]:
    """Serialize local claim creation/settlement with privacy deletion."""

    with _LOCAL_CLAIM_THREAD_LOCK:
        depth = int(getattr(_LOCAL_CLAIM_LOCK_STATE, "depth", 0))
        if depth:
            _LOCAL_CLAIM_LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LOCAL_CLAIM_LOCK_STATE.depth = depth
            return
        lock_path = _claims_dir() / ".claims.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            _LOCAL_CLAIM_LOCK_STATE.depth = 1
            yield
        finally:
            _LOCAL_CLAIM_LOCK_STATE.depth = 0
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


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


def meta_claim_binding_digest(binding_id: str) -> str:
    """Return a non-reversible selector used by authorization deletion."""

    value = str(binding_id or "").strip()
    return hashlib.sha256(f"meta-claim-binding\0{value}".encode()).hexdigest() if value else ""


def _safe_claim_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    """Allow only non-PII selectors needed for HA recovery and deletion."""

    raw = metadata if isinstance(metadata, dict) else {}
    result: dict[str, Any] = {}
    for key in ("binding_id_sha256", "stable_identity_sha256", "inbound_ids_sha256"):
        value = str(raw.get(key) or "").strip().lower()
        if len(value) == 64 and all(char in "0123456789abcdef" for char in value):
            result[key] = value
    event_id = str(raw.get("inbound_event_id") or "").strip().lower()
    if len(event_id) == 44 and event_id.startswith("ibe_") and all(char in "0123456789abcdef" for char in event_id[4:]):
        result["inbound_event_id"] = event_id
    for key in ("inbound_ids_count", "body_fingerprint_count"):
        try:
            count_value = max(0, min(1000, int(raw.get(key) or 0)))
        except (TypeError, ValueError):
            count_value = 0
        result[key] = count_value
    key_kind = str(raw.get("key_kind") or "").strip().lower()
    if key_kind in {"mids_multi", "textbody_slot", "mids", "textbody_only_slot"}:
        result["key_kind"] = key_kind
    return result


def _file_try_claim(
    namespace: str,
    key: str,
    *,
    ttl_seconds: float,
    owner_hash: str,
    metadata: dict[str, Any] | None = None,
    meta_binding_id: str = "",
) -> int:
    path = _file_claim_path(namespace, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with local_event_claim_store_lock():
        if meta_binding_id:
            from services.meta_inbound_deletion_fence import local_binding_deletion_is_fenced

            if local_binding_deletion_is_fenced(meta_binding_id):
                return 0
        now = time.time()
        existing_generation = 0
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                existing_generation = int(data.get("generation") or 0) if isinstance(data, dict) else 0
                created = float(data.get("created_at") or 0)
                expires_at = float(data.get("expires_at_epoch") or 0)
                status = str(data.get("status") or "claimed")
                active_until = expires_at or (created + max(1.0, float(ttl_seconds)))
                if status == "completed" or (status == "claimed" and active_until > now):
                    return 0
            except Exception:
                pass
        tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
        generation = existing_generation + 1
        payload: dict[str, Any] = {
            **_safe_claim_metadata(metadata),
            "namespace": namespace,
            "key_sha256": hashlib.sha256(f"{namespace}\0{key}".encode()).hexdigest(),
            "created_at": now,
            "expires_at_epoch": now + max(1.0, float(ttl_seconds)),
            "status": "claimed",
            "owner_hash": owner_hash,
            "generation": generation,
            "pid": os.getpid(),
        }
        try:
            fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, separators=(",", ":"), sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(str(tmp), str(path))
            os.chmod(path, 0o600)
            return generation
        except Exception:
            return 0
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass


def _file_release(namespace: str, key: str, *, owner_hash: str | None = None) -> None:
    path = _file_claim_path(namespace, key)
    try:
        with local_event_claim_store_lock():
            if path.exists():
                if owner_hash:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if str(data.get("status") or "") != "claimed" or str(data.get("owner_hash") or "") != owner_hash:
                        return
                path.unlink()
    except OSError:
        pass


def get_file_claim_status(namespace: str, key: str) -> dict[str, Any] | None:
    """Read durable file claim status for reconcile diagnostics."""
    path = _file_claim_path(namespace, key)
    with local_event_claim_store_lock():
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return dict(data) if isinstance(data, dict) else None
        except Exception:
            return None


def is_stale_file_claim(
    namespace: str,
    key: str,
    *,
    ttl_seconds: float = 120.0,
) -> bool:
    """True when a claimed lock exists but is older than ttl (abandoned worker)."""
    data = get_file_claim_status(namespace, key)
    if not data:
        return False
    status = str(data.get("status") or "claimed")
    if status == "completed":
        return False
    created = float(data.get("created_at") or 0)
    return bool(created) and (time.time() - created) >= ttl_seconds


def _file_complete(namespace: str, key: str, *, owner_hash: str | None = None) -> None:
    path = _file_claim_path(namespace, key)
    try:
        with local_event_claim_store_lock():
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            if owner_hash and (
                str(data.get("status") or "") != "claimed" or str(data.get("owner_hash") or "") != owner_hash
            ):
                return
            data["status"] = "completed"
            data["owner_hash"] = ""
            data["completed_at"] = time.time()
            tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
            try:
                fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(data, handle, separators=(",", ":"), sort_keys=True)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, path)
            finally:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
    except Exception:
        pass


def _firestore_claim_document_id(
    namespace: str,
    key: str,
    *,
    document_id: str | None = None,
) -> str:
    """Resolve one stable Firestore document id for the entire claim lifecycle."""

    explicit = (document_id or "").strip()
    if explicit:
        return explicit
    return hashlib.sha256(f"{namespace}\0{key}".encode()).hexdigest()


def _firestore_try_claim(
    db: Any,
    *,
    ref: Any,
    namespace: str,
    key: str,
    ttl_seconds: float,
    metadata: dict[str, Any],
    server_timestamp: object,
    owner_hash: str,
    meta_binding_id: str,
) -> int:
    """Create or transactionally reclaim an expired shared claim."""

    now = time.time()
    claim_document = _safe_claim_metadata(metadata)
    claim_document.update(
        {
            "created_at": server_timestamp,
            "created_at_epoch": now,
            "expires_at_epoch": now + max(1.0, float(ttl_seconds)),
            "namespace": namespace[:64],
            "key_sha256": hashlib.sha256(f"{namespace}\0{key}".encode()).hexdigest(),
            "status": "claimed",
            "owner_hash": owner_hash,
        }
    )
    fence_ref = None
    if meta_binding_id:
        from services.meta_inbound_deletion_fence import firestore_binding_deletion_fence_ref

        fence_ref = firestore_binding_deletion_fence_ref(db, meta_binding_id)
    if not hasattr(db, "transaction"):
        if fence_ref is not None and fence_ref.get().exists:
            return 0
        claim_document["generation"] = 1
        ref.create(claim_document)
        return 1

    last_error: Exception | None = None
    for _attempt in range(5):
        transaction = db.transaction()
        try:
            snapshot = ref.get(transaction=transaction)
            if fence_ref is not None and fence_ref.get(transaction=transaction).exists:
                return 0
            if snapshot.exists:
                current = snapshot.to_dict()
                current = current if isinstance(current, dict) else {}
                status = str(current.get("status") or "claimed")
                expires_at = float(current.get("expires_at_epoch") or 0.0)
                if status == "completed":
                    return 0
                if status == "claimed" and expires_at > now:
                    return 0
                if status not in {"claimed", "released"}:
                    raise RuntimeError("Firestore claim state is invalid")
            generation = int(current.get("generation") or 0) + 1 if snapshot.exists else 1
            claim_document["generation"] = generation
            transaction.set(ref, claim_document)
            transaction.commit()
            return generation
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Firestore claim transaction failed") from last_error


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


def _firestore_owner_transition(
    db: Any,
    *,
    ref: Any,
    handle: EventClaimHandle,
    action: str,
    ttl_seconds: float = 0.0,
    server_timestamp: object | None = None,
) -> bool:
    if not hasattr(db, "transaction"):
        snapshot = ref.get()
        current = snapshot.to_dict() if snapshot.exists else {}
        current = current if isinstance(current, dict) else {}
        if (
            str(current.get("status") or "") != "claimed"
            or str(current.get("owner_hash") or "") != handle.owner_hash
            or int(current.get("generation") or 0) != handle.generation
        ):
            return False
        now = time.time()
        if action == "renew":
            current.update({"updated_at_epoch": now, "expires_at_epoch": now + max(1.0, ttl_seconds)})
            ref.set(current)
        elif action == "complete":
            current.update(
                {"status": "completed", "owner_hash": "", "completed_at": server_timestamp, "expires_at_epoch": 0.0}
            )
            ref.set(current)
        elif action == "release":
            ref.delete()
        return True
    last_error: Exception | None = None
    for _attempt in range(5):
        transaction = db.transaction()
        try:
            snapshot = ref.get(transaction=transaction)
            current = snapshot.to_dict() if snapshot.exists else {}
            current = current if isinstance(current, dict) else {}
            if (
                str(current.get("status") or "") != "claimed"
                or str(current.get("owner_hash") or "") != handle.owner_hash
                or int(current.get("generation") or 0) != handle.generation
            ):
                return False
            now = time.time()
            if action == "renew":
                current.update({"updated_at_epoch": now, "expires_at_epoch": now + max(1.0, ttl_seconds)})
            elif action == "complete":
                current.update(
                    {
                        "status": "completed",
                        "owner_hash": "",
                        "completed_at": server_timestamp,
                        "expires_at_epoch": 0.0,
                    }
                )
            elif action == "release":
                current.update(
                    {
                        "status": "released",
                        "owner_hash": "",
                        "released_at": server_timestamp,
                        "expires_at_epoch": 0.0,
                    }
                )
            else:  # pragma: no cover - internal fixed call sites
                raise ValueError("invalid claim transition")
            transaction.set(ref, current)
            transaction.commit()
            return True
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Firestore claim owner transition failed") from last_error


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
