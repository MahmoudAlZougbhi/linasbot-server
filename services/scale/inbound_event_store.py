"""Durable inbound event ledger — authoritative copy outside Valkey.

Valkey/queues may lose jobs on restart; this store is the source of truth for
accepted Meta (and similar) events until a terminal outcome is recorded.
"""

from __future__ import annotations

import json
import time
from typing import Any

from services.scale.inbound_event_store_local import (
    _atomic_json_put,
    _file_get,
    _file_list_active,
    _file_put,
    _path_for,
    _store_dir,
    iter_local_inbound_event_documents,
    local_inbound_event_ledger_lock,
    replace_local_inbound_event_document,
)
from services.scale.inbound_event_store_models import (
    ACTIVE_STATES,
    SAFE_META_SETTINGS_SNAPSHOT_KEYS,
    TERMINAL_STATES,
    EventKind,
    EventState,
    InboundEventRecord,
    InboundEventStateTransitionError,
    InboundEventStoreUnavailableError,
    sanitize_meta_settings_snapshot,
    stable_event_id,
)
from storage.persistent_storage import LOGS_DIR, ensure_dirs

_ = (
    LOGS_DIR,
    _atomic_json_put,
    _path_for,
    ensure_dirs,
)

__all__ = [
    "ACTIVE_STATES",
    "EventKind",
    "EventState",
    "InboundEventRecord",
    "InboundEventStateTransitionError",
    "InboundEventStoreUnavailableError",
    "SAFE_META_SETTINGS_SNAPSHOT_KEYS",
    "TERMINAL_STATES",
    "accountability_stats",
    "create_inbound_event",
    "get_inbound_event",
    "iter_local_inbound_event_documents",
    "list_active_inbound_events",
    "local_inbound_event_ledger_lock",
    "mark_inbound_state",
    "put_inbound_event",
    "replace_local_inbound_event_document",
    "sanitize_meta_settings_snapshot",
    "sanitize_persisted_meta_credentials",
    "stable_event_id",
]


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
