"""File-backed durable event claim storage and owner-handle types."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    # Tests patch LOGS_DIR / ensure_dirs, or replace _claims_dir, on the facade.
    from services import durable_event_claim as facade

    patched = getattr(facade, "_claims_dir", None)
    if patched is not None and patched is not _claims_dir:
        directory = Path(patched())
        directory.mkdir(parents=True, exist_ok=True)
        return directory
    facade.ensure_dirs()
    d = Path(facade.LOGS_DIR) / "durable_claims"
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
