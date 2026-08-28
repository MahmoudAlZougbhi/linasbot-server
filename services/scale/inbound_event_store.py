"""Durable inbound event ledger — authoritative copy outside Valkey.

Valkey/queues may lose jobs on restart; this store is the source of truth for
accepted Meta (and similar) events until a terminal outcome is recorded.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from storage.persistent_storage import LOGS_DIR, ensure_dirs

EventKind = Literal["meta_dm", "meta_comment"]
EventState = Literal[
    "accepted",
    "queued",
    "processing",
    "completed",
    "failed",
    "dead_letter",
]

TERMINAL_STATES = frozenset({"completed", "dead_letter"})
ACTIVE_STATES = frozenset({"accepted", "queued", "processing", "failed"})
SAFE_META_SETTINGS_SNAPSHOT_KEYS = frozenset(
    {
        "enabled",
        "page_id",
        "instagram_account_id",
        "graph_api_version",
        "app_id",
        "app_key",
        "tenant_id",
        "binding_id",
        "auth_flow",
        "graph_base_url",
    }
)
_LOCAL_LEDGER_THREAD_LOCK = threading.RLock()
_LOCAL_LEDGER_LOCK_STATE = threading.local()


class InboundEventStoreUnavailableError(RuntimeError):
    """Raised when the configured shared ledger cannot be read safely."""


class InboundEventStateTransitionError(RuntimeError):
    """Raised when an authoritative inbound state cannot be proven."""


def sanitize_meta_settings_snapshot(data: object) -> dict[str, Any]:
    """Retain non-secret routing metadata and drop all other snapshot fields."""

    raw = data if isinstance(data, dict) else {}
    return {
        str(key): value
        for key, value in raw.items()
        if str(key) in SAFE_META_SETTINGS_SNAPSHOT_KEYS
        and (isinstance(value, (str, bool, int, float)) or value is None)
    }


@dataclass
class InboundEventRecord:
    event_id: str
    kind: EventKind
    tenant_id: str
    claim_namespace: str
    claim_key: str
    state: EventState
    created_at: float
    updated_at: float
    payload: dict[str, Any] = field(default_factory=dict)
    settings_snapshot: dict[str, Any] = field(default_factory=dict)
    binding_snapshot: dict[str, Any] = field(default_factory=dict)
    conversation_key: str = ""
    queue_job_id: str | None = None
    attempts: int = 0
    last_error: str | None = None
    outbound_status: str | None = None
    ai_output_persisted: bool = False
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["settings_snapshot"] = sanitize_meta_settings_snapshot(self.settings_snapshot)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InboundEventRecord:
        return cls(
            event_id=str(data["event_id"]),
            kind=str(data.get("kind") or "meta_dm"),  # type: ignore[arg-type]
            tenant_id=str(data.get("tenant_id") or ""),
            claim_namespace=str(data.get("claim_namespace") or ""),
            claim_key=str(data.get("claim_key") or ""),
            state=str(data.get("state") or "accepted"),  # type: ignore[arg-type]
            created_at=float(data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or time.time()),
            payload=dict(data.get("payload") or {}),
            settings_snapshot=sanitize_meta_settings_snapshot(data.get("settings_snapshot")),
            binding_snapshot=dict(data.get("binding_snapshot") or {}),
            conversation_key=str(data.get("conversation_key") or ""),
            queue_job_id=data.get("queue_job_id"),
            attempts=int(data.get("attempts") or 0),
            last_error=data.get("last_error"),
            outbound_status=data.get("outbound_status"),
            ai_output_persisted=bool(data.get("ai_output_persisted")),
            revision=int(data.get("revision") or 0),
        )


def stable_event_id(kind: str, claim_key: str) -> str:
    digest = hashlib.sha256(f"{kind}\0{claim_key}".encode()).hexdigest()
    return f"ibe_{digest[:40]}"


def _store_dir() -> Path:
    ensure_dirs()
    d = Path(LOGS_DIR) / "inbound_events"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(event_id: str) -> Path:
    return _store_dir() / f"{event_id}.json"


@contextmanager
def local_inbound_event_ledger_lock() -> Iterator[None]:
    """Hold the process/thread-shared exclusive lock for local ledger mutation."""

    with _LOCAL_LEDGER_THREAD_LOCK:
        depth = int(getattr(_LOCAL_LEDGER_LOCK_STATE, "depth", 0))
        if depth:
            _LOCAL_LEDGER_LOCK_STATE.depth = depth + 1
            try:
                yield
            finally:
                _LOCAL_LEDGER_LOCK_STATE.depth = depth
            return

        lock_path = _store_dir() / ".ledger.lock"
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        locked = False
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            locked = True
            _LOCAL_LEDGER_LOCK_STATE.depth = 1
            yield
        finally:
            _LOCAL_LEDGER_LOCK_STATE.depth = 0
            if locked:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _file_put(record: InboundEventRecord) -> None:
    path = _path_for(record.event_id)
    with local_inbound_event_ledger_lock():
        document = record.to_dict()
        binding_id = str(
            record.binding_snapshot.get("binding_id") or record.settings_snapshot.get("binding_id") or ""
        ).strip()
        if binding_id:
            from services.meta_inbound_deletion_fence import local_binding_deletion_is_fenced
            from services.meta_inbound_retention import redacted_inbound_event_tombstone

            if local_binding_deletion_is_fenced(binding_id):
                document = redacted_inbound_event_tombstone(
                    document,
                    reason="authorization_data_deletion",
                    now=time.time(),
                )
        _atomic_json_put(path, document)


def _atomic_json_put(path: Path, data: dict[str, Any]) -> None:
    """Replace one ledger file atomically with owner-only permissions."""

    tmp = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    payload = json.dumps(data, separators=(",", ":"), sort_keys=True)
    try:
        fd = os.open(str(tmp), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(str(tmp), str(path))
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def iter_local_inbound_event_documents() -> Iterator[tuple[Path, dict[str, Any]]]:
    """Yield parseable mappings; hold the public ledger lock for write batches."""

    for path in _store_dir().glob("ibe_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict):
            yield path, raw


def replace_local_inbound_event_document(path: Path, data: dict[str, Any]) -> None:
    """Atomically replace one existing ledger document inside the owned store."""

    with local_inbound_event_ledger_lock():
        root = _store_dir().resolve()
        target = path.resolve()
        if target.parent != root or not target.name.startswith("ibe_") or target.suffix != ".json":
            raise ValueError("Refusing to replace a path outside the inbound-event ledger")
        if not target.is_file():
            raise FileNotFoundError("Inbound-event ledger document is unavailable")
        document = data
        binding_snapshot = data.get("binding_snapshot")
        settings_snapshot = data.get("settings_snapshot")
        binding = binding_snapshot if isinstance(binding_snapshot, dict) else {}
        settings = settings_snapshot if isinstance(settings_snapshot, dict) else {}
        binding_id = str(binding.get("binding_id") or settings.get("binding_id") or "").strip()
        if binding_id:
            from services.meta_inbound_deletion_fence import local_binding_deletion_is_fenced
            from services.meta_inbound_retention import redacted_inbound_event_tombstone

            if local_binding_deletion_is_fenced(binding_id):
                document = redacted_inbound_event_tombstone(
                    data,
                    reason="authorization_data_deletion",
                    now=time.time(),
                )
        _atomic_json_put(target, document)


def _file_get(event_id: str) -> InboundEventRecord | None:
    path = _path_for(event_id)
    if not path.is_file():
        return None
    try:
        return InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def _file_list_active(*, older_than_seconds: float = 0.0) -> list[InboundEventRecord]:
    cutoff = time.time() - max(0.0, older_than_seconds)
    out: list[InboundEventRecord] = []
    root = _store_dir()
    for path in root.glob("ibe_*.json"):
        try:
            rec = InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if rec.state not in ACTIVE_STATES:
            continue
        if rec.updated_at > cutoff:
            continue
        out.append(rec)
    return out


def _firestore_inbound_collection(db: Any) -> Any:
    return db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events")


def _record_from_firestore_snapshot(snapshot: Any) -> InboundEventRecord | None:
    if getattr(snapshot, "exists", True) is False:
        return None
    raw = snapshot.to_dict()
    if not isinstance(raw, dict):
        raise ValueError("Inbound event snapshot is not a mapping")
    return InboundEventRecord.from_dict(raw)


def _shared_active_records(
    collection: Any,
    *,
    local_event_ids: set[str],
) -> dict[str, InboundEventRecord]:
    """Read active shared records plus primary state for every local candidate."""

    from google.cloud.firestore_v1.base_query import FieldFilter

    query = collection.where(filter=FieldFilter("state", "in", sorted(ACTIVE_STATES)))
    primary: dict[str, InboundEventRecord] = {}
    for snapshot in query.stream():
        record = _record_from_firestore_snapshot(snapshot)
        if record is not None:
            primary[record.event_id] = record

    # An active local cache can be stale after a peer completed the shared
    # record. Read its primary document even though terminal records are absent
    # from the active query, otherwise this node could requeue completed work.
    for event_id in local_event_ids - primary.keys():
        record = _record_from_firestore_snapshot(collection.document(event_id).get())
        if record is not None:
            primary[record.event_id] = record
    return primary


def put_inbound_event(
    record: InboundEventRecord,
    *,
    enforce_binding_deletion_fence: bool = False,
    require_shared_existing: bool = False,
) -> InboundEventRecord:
    """Persist without letting any Meta write cross an authorization fence."""
    record.updated_at = time.time()
    binding_id = str(
        record.binding_snapshot.get("binding_id") or record.settings_snapshot.get("binding_id") or ""
    ).strip()
    if (enforce_binding_deletion_fence or require_shared_existing) and not binding_id:
        from services.meta_inbound_deletion_fence import InboundDeletionFenceStoreError

        raise InboundDeletionFenceStoreError("Inbound binding identity is unavailable")

    if binding_id:
        from services.scale.inbound_event_persist import persist_updated_inbound

        # Firestore is the HA fence authority. Local flock is only for the
        # fence check and cache write so ingress cannot serialize the node.
        return InboundEventRecord.from_dict(
            persist_updated_inbound(
                record,
                binding_id=binding_id,
                enforce_binding_deletion_fence=enforce_binding_deletion_fence,
                require_shared_existing=require_shared_existing,
            )
        )

    _file_put(record)
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if db is not None:
            ref = (
                db.collection("artifacts")
                .document("linas-ai-bot-backend")
                .collection("inbound_events")
                .document(record.event_id)
            )
            ref.set(record.to_dict())
    except Exception:
        pass
    return record


def create_inbound_event(
    record: InboundEventRecord,
    *,
    enforce_binding_deletion_fence: bool = False,
) -> tuple[InboundEventRecord, bool]:
    """Create one authoritative inbound row or return the provider redelivery row."""

    record.updated_at = time.time()
    binding_id = str(
        record.binding_snapshot.get("binding_id") or record.settings_snapshot.get("binding_id") or ""
    ).strip()
    if enforce_binding_deletion_fence and not binding_id:
        from services.meta_inbound_deletion_fence import InboundDeletionFenceStoreError

        raise InboundDeletionFenceStoreError("Inbound binding identity is unavailable")
    if not binding_id:
        existing = _file_get(record.event_id)
        if existing is not None:
            return existing, False
        persisted = put_inbound_event(record)
        return persisted, True

    from services.scale.inbound_event_persist import persist_created_inbound

    persisted_document, created = persist_created_inbound(
        record,
        binding_id=binding_id,
        enforce_binding_deletion_fence=enforce_binding_deletion_fence,
    )
    return InboundEventRecord.from_dict(persisted_document), created


def get_inbound_event(
    event_id: str,
    *,
    require_shared_authority: bool = False,
) -> InboundEventRecord | None:
    from config import is_production_runtime

    strict_shared_authority = bool(require_shared_authority or is_production_runtime())
    local = _file_get(event_id)
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if db is None:
            if strict_shared_authority:
                raise InboundEventStoreUnavailableError("Shared inbound-event ledger is unavailable")
            return local
        snap = (
            db.collection("artifacts")
            .document("linas-ai-bot-backend")
            .collection("inbound_events")
            .document(event_id)
            .get()
        )
        if not snap.exists:
            # A local file is only a cache.  Production state transitions must
            # never resurrect a row that the shared authority no longer has.
            if strict_shared_authority:
                return None
            return local
        data = snap.to_dict() or {}
        rec = InboundEventRecord.from_dict(data)
        _file_put(rec)
        return rec
    except InboundEventStoreUnavailableError:
        raise
    except Exception as exc:
        if strict_shared_authority:
            raise InboundEventStoreUnavailableError("Unable to read the shared inbound-event ledger") from exc
        return local


def list_active_inbound_events(*, older_than_seconds: float = 30.0) -> list[InboundEventRecord]:
    """Return deduplicated local + shared reconcile candidates.

    Firestore is the HA authority when configured. Query failures raise instead
    of silently reporting a local-only success that would strand peer events.
    """

    threshold = max(0.0, older_than_seconds)
    cutoff = time.time() - threshold
    from config import is_production_runtime

    strict_shared_authority = bool(is_production_runtime())
    local = _file_list_active(older_than_seconds=threshold)
    local_by_id = {record.event_id: record for record in local}

    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception as exc:
        raise InboundEventStoreUnavailableError("Unable to resolve the shared inbound-event ledger") from exc
    if db is None:
        if strict_shared_authority:
            raise InboundEventStoreUnavailableError("Shared inbound-event ledger is unavailable in production")
        return sorted(local_by_id.values(), key=lambda record: (record.updated_at, record.event_id))

    try:
        collection = _firestore_inbound_collection(db)
        primary_by_id = _shared_active_records(collection, local_event_ids=set(local_by_id))
    except Exception as exc:
        raise InboundEventStoreUnavailableError("Unable to query the shared inbound-event ledger") from exc

    # Cache shared state locally before reconcile mutates it. This is required
    # for a peer-only record, and it also replaces stale active files with a
    # terminal primary record so they cannot reappear on the next watchdog tick.
    for record in primary_by_id.values():
        _file_put(record)

    merged: dict[str, InboundEventRecord] = {}
    for event_id, local_record in local_by_id.items():
        primary_record = primary_by_id.get(event_id)
        if primary_record is None:
            # Legacy/file fallback is test/development-only. In production a
            # local file is a cache, not authority; reconciling an orphan would
            # acquire a global claim and then fail every shared state update.
            if strict_shared_authority:
                continue
            merged[event_id] = local_record
            continue
        if primary_record.state in ACTIVE_STATES and primary_record.updated_at <= cutoff:
            merged[event_id] = primary_record

    for event_id, primary_record in primary_by_id.items():
        if event_id in local_by_id:
            continue
        if primary_record.state in ACTIVE_STATES and primary_record.updated_at <= cutoff:
            merged[event_id] = primary_record
    return sorted(merged.values(), key=lambda record: (record.updated_at, record.event_id))


def mark_inbound_state(
    event_id: str,
    *,
    state: EventState,
    last_error: str | None = None,
    queue_job_id: str | None = None,
    outbound_status: str | None = None,
    ai_output_persisted: bool | None = None,
    bump_attempts: bool = False,
) -> InboundEventRecord:
    from config import is_production_runtime
    from services.meta_inbound_deletion_fence import InboundDeletionFenceStoreError

    require_shared_authority = bool(is_production_runtime())
    for _attempt in range(8):
        rec = get_inbound_event(
            event_id,
            require_shared_authority=require_shared_authority,
        )
        if rec is None:
            raise InboundEventStateTransitionError("Inbound event is unavailable for transition")
        if rec.state in TERMINAL_STATES:
            if state in TERMINAL_STATES:
                return rec
            raise InboundEventStateTransitionError("Inbound event is already terminal")
        rec.state = state
        if last_error is not None:
            rec.last_error = last_error
        if queue_job_id is not None:
            rec.queue_job_id = queue_job_id
        if outbound_status is not None:
            rec.outbound_status = outbound_status
        if ai_output_persisted is not None:
            rec.ai_output_persisted = ai_output_persisted
        if bump_attempts:
            rec.attempts += 1
        try:
            put_inbound_event(
                rec,
                require_shared_existing=require_shared_authority,
            )
        except InboundDeletionFenceStoreError as exc:
            raise InboundEventStateTransitionError("Inbound event disappeared during transition") from exc

        # Never settle the global claim based on the local write result.  A
        # competing node may have won the Firestore revision CAS, so reread the
        # primary row and retry the requested transition while this owner still
        # holds the exact claim capability.
        authoritative = get_inbound_event(
            event_id,
            require_shared_authority=require_shared_authority,
        )
        if authoritative is None:
            raise InboundEventStateTransitionError("Inbound event disappeared during transition")
        if authoritative.state == state:
            return authoritative
        if authoritative.state in TERMINAL_STATES:
            if state in TERMINAL_STATES:
                return authoritative
            raise InboundEventStateTransitionError("Inbound event became terminal during transition")
    raise InboundEventStateTransitionError("Inbound event state transition did not converge")


def accountability_stats(records: list[InboundEventRecord] | None = None) -> dict[str, int]:
    """Count accepted vs terminal for unexplained_missing_events proofs."""
    items = records if records is not None else []
    if records is None:
        root = _store_dir()
        for path in root.glob("ibe_*.json"):
            try:
                items.append(InboundEventRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except Exception:
                continue
    accepted = len(items)
    terminal = sum(1 for r in items if r.state in TERMINAL_STATES)
    active = sum(1 for r in items if r.state in ACTIVE_STATES)
    unexplained_missing = 0
    if records is None:
        from config import is_production_runtime

        if is_production_runtime():
            try:
                from utils.utils import get_firestore_db

                db = get_firestore_db()
                if db is None:
                    raise InboundEventStoreUnavailableError("Shared inbound-event ledger is unavailable in production")
                collection = _firestore_inbound_collection(db)
                # Only active rows can be stranded/replayed. Terminal history
                # is already accounted locally and may be retained for weeks;
                # point-reading it every watchdog minute would make this audit
                # grow without bound.
                for record in (item for item in items if item.state in ACTIVE_STATES):
                    snapshot = collection.document(record.event_id).get()
                    if not snapshot.exists or not isinstance(snapshot.to_dict(), dict):
                        unexplained_missing += 1
            except InboundEventStoreUnavailableError:
                raise
            except Exception as exc:
                raise InboundEventStoreUnavailableError("Unable to audit the shared inbound-event ledger") from exc
    return {
        "accepted_total": accepted,
        "terminal_accounted": terminal,
        "active_non_terminal": active,
        "unexplained_missing_events": unexplained_missing,
    }


def _sanitize_local_meta_credentials(*, apply: bool) -> dict[str, int]:
    root = _store_dir()
    scanned = 0
    changed = 0
    sanitized_count = 0
    errors = 0
    for path in root.glob("ibe_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors += 1
            continue
        if not isinstance(raw, dict):
            errors += 1
            continue
        scanned += 1
        current = raw.get("settings_snapshot")
        sanitized = sanitize_meta_settings_snapshot(current)
        if current == sanitized:
            continue
        changed += 1
        if apply:
            raw["settings_snapshot"] = sanitized
            try:
                replace_local_inbound_event_document(path, raw)
                sanitized_count += 1
            except OSError:
                errors += 1
    return {
        "local_scanned": scanned,
        "local_changed": changed,
        "local_sanitized": sanitized_count,
        "local_errors": errors,
    }


def sanitize_persisted_meta_credentials(
    *,
    apply: bool,
    include_firestore: bool = True,
) -> dict[str, int | bool]:
    """Count or remove historical unsafe settings snapshots without rendering values."""

    if apply:
        # Hold one lock across read + rewrite so a concurrent state transition
        # cannot be overwritten by a stale sanitizer snapshot.
        with local_inbound_event_ledger_lock():
            local = _sanitize_local_meta_credentials(apply=True)
    else:
        local = _sanitize_local_meta_credentials(apply=False)

    firestore_scanned = 0
    firestore_changed = 0
    firestore_sanitized = 0
    firestore_errors = 0
    firestore_available = False
    if include_firestore:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
        if db is None:
            raise RuntimeError("Firestore is unavailable for inbound credential sanitization")
        firestore_available = True
        collection = db.collection("artifacts").document("linas-ai-bot-backend").collection("inbound_events")
        for snapshot in collection.select(["settings_snapshot"]).stream():
            firestore_scanned += 1
            try:
                raw = snapshot.to_dict() or {}
            except Exception:
                firestore_errors += 1
                continue
            if not isinstance(raw, dict):
                firestore_errors += 1
                continue
            current = raw.get("settings_snapshot")
            sanitized = sanitize_meta_settings_snapshot(current)
            if current == sanitized:
                continue
            firestore_changed += 1
            if apply:
                try:
                    snapshot.reference.update({"settings_snapshot": sanitized})
                    firestore_sanitized += 1
                except Exception:
                    firestore_errors += 1

    return {
        "apply": apply,
        **local,
        "firestore_available": firestore_available,
        "firestore_scanned": firestore_scanned,
        "firestore_changed": firestore_changed,
        "firestore_sanitized": firestore_sanitized,
        "firestore_errors": firestore_errors,
    }
