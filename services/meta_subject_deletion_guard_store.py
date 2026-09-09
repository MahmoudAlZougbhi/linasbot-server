"""Firestore accessors for the Meta OAuth/deletion subject boundary."""

from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Literal

from services.meta_subject_deletion_guard_models import (
    _CONFIRMATION_CODE_RE,
    _DEAUTHORIZATION_COLLECTION,
    _DEAUTHORIZATION_SAFE_FIELDS,
    _FIRESTORE_APP_ID,
    _INDEX_SAFE_FIELDS,
    _LEASE_COLLECTION,
    _LEASE_SAFE_FIELDS,
    _REQUEST_COLLECTION,
    _REQUEST_SAFE_FIELDS,
    _SCHEMA_VERSION,
    _SUBJECT_INDEX_COLLECTION,
    MetaSubjectDeletionGuardError,
    MetaSubjectDeletionSnapshot,
    MetaSubjectDeletionStoreUnavailableError,
)


def _firestore_db() -> Any:
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception as exc:
        raise MetaSubjectDeletionStoreUnavailableError("Meta subject guard store is unavailable") from exc
    if db is None:
        raise MetaSubjectDeletionStoreUnavailableError("Meta subject guard store is unavailable")
    return db


def _app_document(db: Any) -> Any:
    return db.collection("artifacts").document(_FIRESTORE_APP_ID)


def _lease_ref(db: Any, subject_key: str) -> Any:
    return _app_document(db).collection(_LEASE_COLLECTION).document(subject_key)


def _index_ref(db: Any, subject_key: str) -> Any:
    return _app_document(db).collection(_SUBJECT_INDEX_COLLECTION).document(subject_key)


def _request_ref(db: Any, confirmation_code: str) -> Any:
    return _app_document(db).collection(_REQUEST_COLLECTION).document(confirmation_code)


def _deauthorization_ref(db: Any, subject_key: str) -> Any:
    return _app_document(db).collection(_DEAUTHORIZATION_COLLECTION).document(subject_key)


def _snapshot_dict(snapshot: Any) -> dict[str, Any]:
    try:
        value = snapshot.to_dict()
    except Exception as exc:
        raise MetaSubjectDeletionGuardError("Meta subject guard state is invalid") from exc
    if not isinstance(value, dict):
        raise MetaSubjectDeletionGuardError("Meta subject guard state is invalid")
    return value


def _safe_number(value: object, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise MetaSubjectDeletionGuardError("Meta subject guard state is invalid")
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise MetaSubjectDeletionGuardError("Meta subject guard state is invalid") from exc
    if not math.isfinite(parsed) or parsed < minimum:
        raise MetaSubjectDeletionGuardError("Meta subject guard state is invalid")
    return parsed


def _capture_snapshot(db: Any, subject_key: str, transaction: Any) -> MetaSubjectDeletionSnapshot:
    deauthorization_snapshot = _deauthorization_ref(db, subject_key).get(transaction=transaction)
    deauthorization: dict[str, Any] = {}
    if deauthorization_snapshot.exists:
        deauthorization = _snapshot_dict(deauthorization_snapshot)
        if (
            not set(deauthorization).issubset(_DEAUTHORIZATION_SAFE_FIELDS)
            or deauthorization.get("schema_version") != _SCHEMA_VERSION
        ):
            raise MetaSubjectDeletionGuardError("Meta deauthorization state is invalid")
        generation_value = _safe_number(deauthorization.get("generation"), minimum=1.0)
        if not generation_value.is_integer():
            raise MetaSubjectDeletionGuardError("Meta deauthorization state is invalid")
        _safe_number(deauthorization.get("deauthorized_at"), minimum=1.0)
    deauthorization_generation = int(deauthorization.get("generation") or 0)
    deauthorized_at = float(deauthorization.get("deauthorized_at") or 0.0)
    index_snapshot = _index_ref(db, subject_key).get(transaction=transaction)
    if not index_snapshot.exists:
        canonical = json.dumps(
            {"deauthorization": deauthorization, "deletion": "none"},
            separators=(",", ":"),
            sort_keys=True,
        )
        return MetaSubjectDeletionSnapshot(
            state="none",
            generation=0,
            fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
            deauthorization_generation=deauthorization_generation,
            deauthorized_at=deauthorized_at,
            deletion_boundary_at=0.0,
        )
    index = _snapshot_dict(index_snapshot)
    if not set(index).issubset(_INDEX_SAFE_FIELDS) or index.get("schema_version") != _SCHEMA_VERSION:
        raise MetaSubjectDeletionGuardError("Meta deletion subject index is invalid")
    confirmation_code = str(index.get("confirmation_code") or "").strip().lower()
    if not _CONFIRMATION_CODE_RE.fullmatch(confirmation_code):
        raise MetaSubjectDeletionGuardError("Meta deletion subject index is invalid")
    request_snapshot = _request_ref(db, confirmation_code).get(transaction=transaction)
    if not request_snapshot.exists:
        raise MetaSubjectDeletionGuardError("Meta deletion request is unavailable")
    request = _snapshot_dict(request_snapshot)
    if not set(request).issubset(_REQUEST_SAFE_FIELDS) or request.get("schema_version") != _SCHEMA_VERSION:
        raise MetaSubjectDeletionGuardError("Meta deletion request is invalid")
    if str(request.get("confirmation_code") or "").strip().lower() != confirmation_code:
        raise MetaSubjectDeletionGuardError("Meta deletion request is invalid")
    state = str(request.get("state") or "").strip()
    if state not in {"pending", "completed", "no_data", "failed"}:
        raise MetaSubjectDeletionGuardError("Meta deletion request is invalid")
    generation_value = _safe_number(request.get("generation"), minimum=1.0)
    if not generation_value.is_integer():
        raise MetaSubjectDeletionGuardError("Meta deletion request is invalid")
    generation = int(generation_value)
    requested_at = _safe_number(request.get("requested_at"), minimum=1.0)
    updated_at = _safe_number(request.get("updated_at"), minimum=requested_at)
    completed_at = 0.0
    if state in {"completed", "no_data"}:
        completed_at = _safe_number(request.get("completed_at"), minimum=requested_at)
    deletion_boundary_at = max(requested_at, updated_at, completed_at)
    canonical = json.dumps(
        {"deauthorization": deauthorization, "index": index, "request": request},
        separators=(",", ":"),
        sort_keys=True,
    )
    return MetaSubjectDeletionSnapshot(
        state=state,  # type: ignore[arg-type]
        generation=generation,
        fingerprint=hashlib.sha256(canonical.encode()).hexdigest(),
        deauthorization_generation=deauthorization_generation,
        deauthorized_at=deauthorized_at,
        deletion_boundary_at=deletion_boundary_at,
    )


def _lease_document(
    *,
    owner_hash: str,
    purpose: Literal["oauth", "deletion", "deauthorization", "released"],
    acquired_at: float,
    updated_at: float,
    expires_at: float,
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "owner_hash": owner_hash,
        "purpose": purpose,
        "acquired_at": acquired_at,
        "updated_at": updated_at,
        "expires_at": expires_at,
    }


def _parse_lease(value: object) -> tuple[str, str, float]:
    if not isinstance(value, dict) or not set(value).issubset(_LEASE_SAFE_FIELDS):
        raise MetaSubjectDeletionGuardError("Meta subject lease is invalid")
    if value.get("schema_version") != _SCHEMA_VERSION:
        raise MetaSubjectDeletionGuardError("Meta subject lease is invalid")
    owner_hash = str(value.get("owner_hash") or "")
    purpose = str(value.get("purpose") or "")
    if purpose not in {"oauth", "deletion", "deauthorization", "released"}:
        raise MetaSubjectDeletionGuardError("Meta subject lease is invalid")
    if owner_hash and not re.fullmatch(r"[0-9a-f]{64}", owner_hash):
        raise MetaSubjectDeletionGuardError("Meta subject lease is invalid")
    _safe_number(value.get("acquired_at"))
    _safe_number(value.get("updated_at"))
    expires_at = _safe_number(value.get("expires_at"))
    if (purpose == "released" and (owner_hash or expires_at != 0.0)) or (
        purpose in {"oauth", "deletion", "deauthorization"} and (not owner_hash or expires_at <= 0.0)
    ):
        raise MetaSubjectDeletionGuardError("Meta subject lease is invalid")
    return owner_hash, purpose, expires_at
