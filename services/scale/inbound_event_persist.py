"""Persist inbound rows without holding the local ledger flock over Firestore."""

from __future__ import annotations

from typing import Any


def reject_if_locally_fenced(binding_id: str, *, enforce: bool) -> bool:
    """Return local fence state. Raises when a create must not proceed."""

    from services.meta_inbound_deletion_fence import (
        InboundBindingDeletionFencedError,
        local_binding_deletion_is_fenced,
    )
    from services.scale.inbound_event_store import local_inbound_event_ledger_lock

    with local_inbound_event_ledger_lock():
        fenced = local_binding_deletion_is_fenced(binding_id)
    if enforce and fenced:
        raise InboundBindingDeletionFencedError("Meta authorization is being deleted")
    return fenced


def cache_local_inbound_document(
    *,
    event_id: str,
    binding_id: str,
    document: dict[str, Any],
    now: float,
) -> dict[str, Any]:
    """Write the local cache after the shared ledger commit.

    If deletion fenced the binding while Firestore was in flight, store a
    tombstone locally. Firestore remains the scan authority for deletion.
    """

    from services.meta_inbound_deletion_fence import local_binding_deletion_is_fenced
    from services.meta_inbound_retention import redacted_inbound_event_tombstone
    from services.scale.inbound_event_store import (
        _atomic_json_put,
        _path_for,
        local_inbound_event_ledger_lock,
    )

    persisted = dict(document)
    with local_inbound_event_ledger_lock():
        if binding_id and local_binding_deletion_is_fenced(binding_id):
            persisted = redacted_inbound_event_tombstone(
                persisted,
                reason="authorization_data_deletion",
                now=now,
            )
        _atomic_json_put(_path_for(event_id), persisted)
    return persisted


def persist_updated_inbound(
    record: Any,
    *,
    binding_id: str,
    enforce_binding_deletion_fence: bool,
    require_shared_existing: bool,
) -> dict[str, Any]:
    """Commit an inbound update to Firestore, then refresh the local cache."""

    from services.meta_inbound_deletion_fence import (
        InboundDeletionFenceStoreError,
        persist_firestore_event_respecting_fence,
        persist_firestore_event_unless_fenced,
    )
    from services.meta_inbound_retention import redacted_inbound_event_tombstone

    local_fenced = reject_if_locally_fenced(
        binding_id,
        enforce=enforce_binding_deletion_fence,
    )
    document = record.to_dict()
    if local_fenced:
        document = redacted_inbound_event_tombstone(
            document,
            reason="authorization_data_deletion",
            now=record.updated_at,
        )
    try:
        if enforce_binding_deletion_fence:
            persist_firestore_event_unless_fenced(
                binding_id=binding_id,
                event_id=record.event_id,
                document=document,
            )
            persisted = document
        else:
            persisted = persist_firestore_event_respecting_fence(
                binding_id=binding_id,
                event_id=record.event_id,
                document=document,
                require_existing=require_shared_existing,
            )
    except InboundDeletionFenceStoreError:
        if enforce_binding_deletion_fence or require_shared_existing:
            raise
        # Local fence is authoritative on this node. If the shared store is
        # temporarily unavailable, never trade its tombstone for plaintext.
        persisted = document
    return cache_local_inbound_document(
        event_id=record.event_id,
        binding_id=binding_id,
        document=persisted,
        now=record.updated_at,
    )


def _create_soak_firestore_event(record: Any) -> tuple[dict[str, Any], bool]:
    """Write a unique soak inbound row with one Firestore create, not a txn get+set.

    Soak event IDs are unique. Production Meta still uses the transactional
    create so provider redelivery cannot reset an existing row. Firestore
    remains the authoritative copy; the local JSON cache is skipped because
    soak workers do not read it.
    """

    from google.api_core.exceptions import AlreadyExists

    from services.meta_inbound_deletion_fence import (
        InboundDeletionFenceStoreError,
        _firestore_event_ref,
    )
    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if db is None:
        raise InboundDeletionFenceStoreError("Firestore inbound fence store is unavailable")
    persisted = dict(record.to_dict())
    persisted["revision"] = max(1, int(persisted.get("revision") or 0))
    event_ref = _firestore_event_ref(db, str(record.event_id))
    try:
        event_ref.create(persisted)
        return persisted, True
    except AlreadyExists:
        snapshot = event_ref.get()
        current = snapshot.to_dict() if snapshot.exists else None
        if isinstance(current, dict):
            return current, False
        raise InboundDeletionFenceStoreError("Firestore inbound event is invalid") from None


def persist_created_inbound(
    record: Any,
    *,
    binding_id: str,
    enforce_binding_deletion_fence: bool,
) -> tuple[dict[str, Any], bool]:
    """Create the shared inbound row, then refresh the local cache."""

    from services.meta_inbound_deletion_fence import create_firestore_event_unless_fenced

    payload = getattr(record, "payload", None)
    soak = isinstance(payload, dict) and bool(payload.get("_linas_soak_simulation"))
    if soak:
        from services.scale.soak_arm import is_armed

        if is_armed():
            return _create_soak_firestore_event(record)
    reject_if_locally_fenced(binding_id, enforce=enforce_binding_deletion_fence)
    persisted_document, created = create_firestore_event_unless_fenced(
        binding_id=binding_id,
        event_id=record.event_id,
        document=record.to_dict(),
    )
    persisted_document = cache_local_inbound_document(
        event_id=record.event_id,
        binding_id=binding_id,
        document=persisted_document,
        now=record.updated_at,
    )
    return persisted_document, created
