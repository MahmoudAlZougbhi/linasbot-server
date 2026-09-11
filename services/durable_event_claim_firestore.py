"""Firestore create-if-absent and owner-generation transitions for event claims."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from services.durable_event_claim_file import EventClaimHandle, _safe_claim_metadata


def _is_already_exists(exc: BaseException) -> bool:
    if type(exc).__name__ in ("AlreadyExists", "Conflict"):
        return True
    code = getattr(exc, "code", None)
    if code in (409, "ALREADY_EXISTS"):
        return True
    s = str(exc).lower()
    return "already exists" in s or "already_exists" in s


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

    from services.firestore_transaction_compat import run_firestore_transaction

    last_error: Exception | None = None
    for _attempt in range(5):
        try:

            def _claim(transaction: Any) -> int:
                snapshot = ref.get(transaction=transaction)
                if fence_ref is not None and fence_ref.get(transaction=transaction).exists:
                    return 0
                current: dict[str, Any] = {}
                if snapshot.exists:
                    loaded = snapshot.to_dict()
                    current = loaded if isinstance(loaded, dict) else {}
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
                return generation

            return run_firestore_transaction(db, _claim)
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Firestore claim transaction failed") from last_error


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
    from services.firestore_transaction_compat import run_firestore_transaction

    last_error: Exception | None = None
    for _attempt in range(5):
        try:

            def _transition(transaction: Any) -> bool:
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
                return True

            return run_firestore_transaction(db, _transition)
        except Exception as exc:
            last_error = exc
    raise RuntimeError("Firestore claim owner transition failed") from last_error
