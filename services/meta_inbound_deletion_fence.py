"""Durable binding fences that serialize Meta ingress with authorization deletion."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

_FIRESTORE_APP_ID = "linas-ai-bot-backend"
_FENCE_COLLECTION = "inbound_deletion_fences"


class InboundBindingDeletionFencedError(RuntimeError):
    """Raised when ingress targets an authorization being deleted."""


class InboundDeletionFenceStoreError(RuntimeError):
    """Raised when a required fence store cannot be read or written."""


def _binding_id(value: object) -> str:
    binding_id = str(value or "").strip()
    if not binding_id or len(binding_id) > 128:
        raise InboundDeletionFenceStoreError("Inbound binding identity is invalid")
    return binding_id


def _fence_key(binding_id: str) -> str:
    return hashlib.sha256(f"meta-inbound-deletion:{binding_id}".encode()).hexdigest()


def _local_fence_path(binding_id: str) -> Path:
    from services.scale import inbound_event_store as event_store

    return event_store._store_dir() / f".binding_deletion_{_fence_key(binding_id)}.json"


def local_binding_deletion_is_fenced(binding_id: str) -> bool:
    """Return the local fence state; callers serialize with the ledger lock."""

    return _local_fence_path(_binding_id(binding_id)).is_file()


def _firestore_fence_ref(db: Any, binding_id: str) -> Any:
    return (
        db.collection("artifacts")
        .document(_FIRESTORE_APP_ID)
        .collection(_FENCE_COLLECTION)
        .document(_fence_key(binding_id))
    )


def firestore_binding_deletion_fence_ref(db: Any, binding_id: str) -> Any:
    """Return the exact fence ref for an atomic binding-scoped transaction."""

    return _firestore_fence_ref(db, _binding_id(binding_id))


def _firestore_event_ref(db: Any, event_id: str) -> Any:
    return db.collection("artifacts").document(_FIRESTORE_APP_ID).collection("inbound_events").document(event_id)


def _shared_fence_exists(fence_ref: Any) -> bool:
    snapshot = fence_ref.get()
    return bool(getattr(snapshot, "exists", False))


def _tombstone_shared_event_if_fenced(
    *,
    fence_ref: Any,
    event_ref: Any,
    document: dict[str, Any],
) -> dict[str, Any] | None:
    """Overwrite a just-committed row if deletion fenced the binding in flight."""

    if not _shared_fence_exists(fence_ref):
        return None
    from services.meta_inbound_retention import redacted_inbound_event_tombstone

    tombstone = redacted_inbound_event_tombstone(
        document,
        reason="authorization_data_deletion",
        now=time.time(),
    )
    event_ref.set(tombstone)
    return tombstone


def persist_firestore_event_unless_fenced(
    *,
    binding_id: str,
    event_id: str,
    document: dict[str, Any],
) -> None:
    """Reject a new event when its binding fence exists.

    The fence is checked around the event-row transaction, not inside it, so
    inbound creates for one binding are not serialized on the fence document.
    Either the event commits before the fence (deletion's later scan sees it),
    or the fence wins and the row is not accepted / is tombstoned.
    """

    persist_firestore_event_respecting_fence(
        binding_id=binding_id,
        event_id=event_id,
        document=document,
        reject_if_fenced=True,
    )


def create_firestore_event_unless_fenced(
    *,
    binding_id: str,
    event_id: str,
    document: dict[str, Any],
    skip_shared_fence_reads: bool = False,
) -> tuple[dict[str, Any], bool]:
    """Create the inbound ledger row after checking its deletion fence.

    The fence document is read outside the event-row transaction so concurrent
    inbound creates for one binding are not serialized on that fence.  A
    provider redelivery returns the already-authoritative row instead of
    resetting its state.  This lets webhook code persist before acquiring the
    processing claim without creating a claim-without-ledger loss window.
    """

    from utils.utils import get_firestore_db

    target_binding = _binding_id(binding_id)
    db = get_firestore_db()
    if db is None:
        raise InboundDeletionFenceStoreError("Firestore inbound fence store is unavailable")
    fence_ref = None if skip_shared_fence_reads else _firestore_fence_ref(db, target_binding)
    event_ref = _firestore_event_ref(db, str(event_id))
    from services.firestore_transaction_compat import run_firestore_transaction

    last_error: Exception | None = None
    for _attempt in range(5):
        try:
            if fence_ref is not None and _shared_fence_exists(fence_ref):
                raise InboundBindingDeletionFencedError("Meta authorization is being deleted")

            def _create(transaction: Any) -> tuple[dict[str, Any], bool]:
                current_snapshot = event_ref.get(transaction=transaction)
                if current_snapshot.exists:
                    current = current_snapshot.to_dict()
                    if not isinstance(current, dict):
                        raise InboundDeletionFenceStoreError("Firestore inbound event is invalid")
                    return current, False
                persisted = dict(document)
                persisted["revision"] = max(1, int(persisted.get("revision") or 0))
                transaction.set(event_ref, persisted)
                return persisted, True

            persisted_document, created = run_firestore_transaction(db, _create)
            if fence_ref is not None and (
                _tombstone_shared_event_if_fenced(
                    fence_ref=fence_ref,
                    event_ref=event_ref,
                    document=persisted_document,
                )
                is not None
            ):
                raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
            return persisted_document, created
        except (InboundBindingDeletionFencedError, InboundDeletionFenceStoreError):
            raise
        except Exception as exc:
            last_error = exc
            try:
                committed = event_ref.get()
                if committed.exists:
                    current = committed.to_dict()
                    if isinstance(current, dict):
                        if fence_ref is not None and (
                            _tombstone_shared_event_if_fenced(
                                fence_ref=fence_ref,
                                event_ref=event_ref,
                                document=current,
                            )
                            is not None
                        ):
                            raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
                        return current, False
                if fence_ref is not None and fence_ref.get().exists:
                    raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
            except InboundBindingDeletionFencedError:
                raise
            except Exception:
                pass
    raise InboundDeletionFenceStoreError("Firestore inbound create transaction failed") from last_error


_UNDELIVERED_REOPEN_OUTBOUND = frozenset({"unknown", "needs_owner_action", "undelivered_retry"})


def _allow_completed_undelivered_reopen(current: dict[str, Any], incoming: dict[str, Any]) -> bool:
    """Allow one explicit Meta DM reopen after Graph never accepted a send."""
    if str(current.get("kind") or "") != "meta_dm":
        return False
    raw_payload = current.get("payload")
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    if bool(payload.get("_linas_soak_simulation")):
        return False
    outbound = str(current.get("outbound_status") or "").strip().lower()
    if outbound not in _UNDELIVERED_REOPEN_OUTBOUND:
        return False
    if str(incoming.get("state") or "") != "accepted":
        return False
    return str(incoming.get("outbound_status") or "").strip().lower() == "undelivered_retry"


def persist_firestore_event_respecting_fence(
    *,
    binding_id: str,
    event_id: str,
    document: dict[str, Any],
    reject_if_fenced: bool = False,
    require_existing: bool = False,
) -> dict[str, Any]:
    """Persist an event without allowing a stale writer to cross a fence.

    Acceptance rejects a fenced authorization.  State transitions instead
    replace the shared row with a closed-schema tombstone so an old in-memory
    record can never restore payload or unknown fields after deletion.
    """

    from services.meta_inbound_retention import redacted_inbound_event_tombstone
    from utils.utils import get_firestore_db

    target_binding = _binding_id(binding_id)
    db = get_firestore_db()
    if db is None:
        raise InboundDeletionFenceStoreError("Firestore inbound fence store is unavailable")
    fence_ref = _firestore_fence_ref(db, target_binding)
    event_ref = _firestore_event_ref(db, str(event_id))
    from services.firestore_transaction_compat import run_firestore_transaction

    last_error: Exception | None = None
    for _attempt in range(5):
        persisted = document
        try:
            if _shared_fence_exists(fence_ref):
                if reject_if_fenced:
                    raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
                current_snapshot = event_ref.get()
                current = current_snapshot.to_dict() if getattr(current_snapshot, "exists", False) else None
                source = current if isinstance(current, dict) else document
                persisted = redacted_inbound_event_tombstone(
                    source,
                    reason="authorization_data_deletion",
                    now=time.time(),
                )
                event_ref.set(persisted)
                return persisted

            def _persist(transaction: Any) -> dict[str, Any]:
                nonlocal persisted
                current_snapshot = event_ref.get(transaction=transaction)
                current = current_snapshot.to_dict() if current_snapshot.exists else None
                current = current if isinstance(current, dict) else None
                if current is None and require_existing:
                    raise InboundDeletionFenceStoreError("Firestore inbound event is unavailable for transition")
                if current is not None:
                    current_state = str(current.get("state") or "")
                    incoming_revision = int(document.get("revision") or 0)
                    current_revision = int(current.get("revision") or 0)
                    if incoming_revision != current_revision:
                        return current
                    if current_state in {"completed", "dead_letter"}:
                        if current_state == "dead_letter" or not _allow_completed_undelivered_reopen(current, document):
                            return current
                    persisted = dict(document)
                    persisted["revision"] = current_revision + 1
                else:
                    persisted = dict(document)
                    persisted["revision"] = max(1, int(persisted.get("revision") or 0))
                transaction.set(event_ref, persisted)
                return persisted

            persisted = run_firestore_transaction(db, _persist)
            tombstoned = _tombstone_shared_event_if_fenced(
                fence_ref=fence_ref,
                event_ref=event_ref,
                document=persisted,
            )
            if tombstoned is not None:
                if reject_if_fenced:
                    raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
                return tombstoned
            return persisted
        except (InboundBindingDeletionFencedError, InboundDeletionFenceStoreError):
            raise
        except Exception as exc:
            last_error = exc
            try:
                committed = event_ref.get()
                if committed.exists and committed.to_dict() == persisted:
                    tombstoned = _tombstone_shared_event_if_fenced(
                        fence_ref=fence_ref,
                        event_ref=event_ref,
                        document=persisted,
                    )
                    if tombstoned is not None:
                        if reject_if_fenced:
                            raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
                        return tombstoned
                    return persisted
                if reject_if_fenced and fence_ref.get().exists:
                    raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
            except InboundBindingDeletionFencedError:
                raise
            except Exception:
                pass
    raise InboundDeletionFenceStoreError("Firestore inbound fence transaction failed") from last_error


def _write_local_fence(binding_id: str, *, created_at: float) -> bool:
    path = _local_fence_path(binding_id)
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InboundDeletionFenceStoreError("Local inbound deletion fence is invalid") from exc
        if not isinstance(existing, dict) or existing.get("binding_id") != binding_id:
            raise InboundDeletionFenceStoreError("Local inbound deletion fence is invalid")
        return False
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    payload = json.dumps(
        {"binding_id": binding_id, "created_at": created_at},
        separators=(",", ":"),
        sort_keys=True,
    )
    try:
        fd = os.open(str(temporary), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return True


def install_local_inbound_binding_deletion_fences(
    binding_ids: set[str] | frozenset[str],
    *,
    now: float | None = None,
) -> dict[str, int]:
    """Install deletion fences only in this node's private inbound ledger."""

    from services.scale import inbound_event_store as event_store

    targets = tuple(sorted({_binding_id(value) for value in binding_ids}))
    stats = {"local_fenced": 0}
    if not targets:
        return stats
    created_at = time.time() if now is None else float(now)
    try:
        with event_store.local_inbound_event_ledger_lock():
            for binding_id in targets:
                if _write_local_fence(binding_id, created_at=created_at):
                    stats["local_fenced"] += 1
    except InboundDeletionFenceStoreError:
        raise
    except (OSError, ValueError) as exc:
        raise InboundDeletionFenceStoreError("Inbound deletion fence write failed") from exc
    return stats


def install_inbound_binding_deletion_fences(
    binding_ids: set[str] | frozenset[str],
    *,
    now: float | None = None,
) -> dict[str, int]:
    """Permanently fence exact bindings in Firestore, then the local ledger."""

    from services.scale import inbound_event_store as event_store
    from utils.utils import get_firestore_db

    targets = tuple(sorted({_binding_id(value) for value in binding_ids}))
    stats = {"firestore_fenced": 0, "local_fenced": 0}
    if not targets:
        return stats
    created_at = time.time() if now is None else float(now)
    db = get_firestore_db()
    if db is None:
        raise InboundDeletionFenceStoreError("Firestore inbound fence store is unavailable")
    try:
        with event_store.local_inbound_event_ledger_lock():
            for binding_id in targets:
                _firestore_fence_ref(db, binding_id).set({"binding_id": binding_id, "created_at": created_at})
                stats["firestore_fenced"] += 1
            for binding_id in targets:
                if _write_local_fence(binding_id, created_at=created_at):
                    stats["local_fenced"] += 1
    except InboundDeletionFenceStoreError:
        raise
    except (OSError, ValueError) as exc:
        raise InboundDeletionFenceStoreError("Inbound deletion fence write failed") from exc
    except Exception as exc:
        raise InboundDeletionFenceStoreError("Firestore inbound deletion fence write failed") from exc
    return stats
