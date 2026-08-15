"""Firestore subject lease that serializes Meta OAuth with data deletion."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from services.meta_app_registry_common import AuthFlow

_FIRESTORE_APP_ID = "linas-ai-bot-backend"
_SUBJECT_INDEX_COLLECTION = "meta_deletion_subject_index"
_REQUEST_COLLECTION = "meta_deletion_requests"
_LEASE_COLLECTION = "meta_deletion_subject_leases"
_DEAUTHORIZATION_COLLECTION = "meta_deauthorization_subjects"
_SCHEMA_VERSION = 1
_DEFAULT_LEASE_SECONDS = 300.0
_DEFAULT_DELETION_WAIT_SECONDS = 30.0
_SUBJECT_KEY_RE = re.compile(r"^[0-9a-f]{64}$")
_CONFIRMATION_CODE_RE = re.compile(r"^[0-9a-f]{32}$")
_META_USER_ID_RE = re.compile(r"^[0-9]{3,64}$")
_INDEX_SAFE_FIELDS = frozenset({"schema_version", "confirmation_code", "created_at"})
_REQUEST_SAFE_FIELDS = frozenset(
    {
        "schema_version",
        "confirmation_code",
        "app_key",
        "app_id",
        "auth_flow",
        "bindings",
        "current_bindings",
        "generation",
        "required_nodes",
        "state",
        "coordinator_state",
        "requested_at",
        "updated_at",
        "completed_at",
        "revoked_bindings",
        "shared_redacted_documents",
        "redacted_ledger_documents",
        "safe_error",
    }
)
_LEASE_SAFE_FIELDS = frozenset({"schema_version", "owner_hash", "purpose", "acquired_at", "updated_at", "expires_at"})
_DEAUTHORIZATION_SAFE_FIELDS = frozenset({"schema_version", "generation", "deauthorized_at"})


class MetaSubjectDeletionGuardError(RuntimeError):
    """Base error for the OAuth/deletion subject boundary."""


class MetaSubjectDeletionStoreUnavailableError(MetaSubjectDeletionGuardError):
    """Raised when Firestore cannot enforce the subject boundary."""


class MetaSubjectDeletionLeaseBusyError(MetaSubjectDeletionGuardError):
    """Raised when another live owner holds the subject lease."""


class MetaSubjectDeletionBlockedError(MetaSubjectDeletionGuardError):
    """Raised when OAuth is blocked by pending or failed deletion."""


class MetaSubjectDeletionChangedError(MetaSubjectDeletionGuardError):
    """Raised when deletion state changes during OAuth provider work."""


@dataclass(frozen=True)
class MetaSubjectDeletionSnapshot:
    """Safe request fingerprint captured before OAuth provider mutation."""

    state: Literal["none", "pending", "completed", "no_data", "failed"]
    generation: int
    fingerprint: str
    deauthorization_generation: int = 0
    deauthorized_at: float = 0.0
    deletion_boundary_at: float = 0.0

    @property
    def oauth_allowed(self) -> bool:
        return self.state in {"none", "completed", "no_data"}

    def oauth_allowed_for(self, oauth_started_at: float) -> bool:
        started_at = float(oauth_started_at)
        if not self.oauth_allowed:
            return False
        if self.deauthorization_generation and started_at <= self.deauthorized_at:
            return False
        if self.state in {"completed", "no_data"} and started_at <= self.deletion_boundary_at:
            return False
        return True


def meta_deletion_subject_hmac(
    *,
    app_key: str,
    app_id: str,
    auth_flow: AuthFlow,
    meta_user_id: str,
    app_secret: str,
) -> str:
    """Return the existing secret-keyed subject index without exposing its ID."""

    resolved_app_key = str(app_key or "").strip()
    resolved_app_id = str(app_id or "").strip()
    resolved_user_id = str(meta_user_id or "").strip()
    resolved_secret = str(app_secret or "").strip()
    if (
        not resolved_app_key
        or len(resolved_app_key) > 64
        or not resolved_app_id.isdigit()
        or auth_flow not in {"facebook_login", "instagram_login"}
        or not _META_USER_ID_RE.fullmatch(resolved_user_id)
        or not resolved_secret
    ):
        raise MetaSubjectDeletionGuardError("Meta deletion subject identity is invalid")
    return hmac.new(
        resolved_secret.encode("utf-8"),
        (f"meta-deletion-index:{resolved_app_key}:{resolved_app_id}:{auth_flow}:{resolved_user_id}").encode(),
        hashlib.sha256,
    ).hexdigest()


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


@dataclass
class MetaSubjectDeletionLease:
    """One owner-verified, crash-expiring Firestore subject lease."""

    db: Any
    subject_key: str
    owner_token: str = field(repr=False)
    purpose: Literal["oauth", "deletion", "deauthorization"]
    acquired_at: float
    lease_seconds: float
    snapshot: MetaSubjectDeletionSnapshot | None = None
    oauth_started_at: float = 0.0

    @property
    def owner_hash(self) -> str:
        return hashlib.sha256(self.owner_token.encode()).hexdigest()

    def _renew(self, *, expected_snapshot: MetaSubjectDeletionSnapshot | None) -> MetaSubjectDeletionSnapshot | None:
        reference = _lease_ref(self.db, self.subject_key)
        last_error: Exception | None = None
        for _attempt in range(5):
            try:
                now = time.time()
                transaction = self.db.transaction()
                lease_snapshot = reference.get(transaction=transaction)
                if not lease_snapshot.exists:
                    raise MetaSubjectDeletionChangedError("Meta subject lease was lost")
                current_owner, current_purpose, expires_at = _parse_lease(_snapshot_dict(lease_snapshot))
                if (
                    not hmac.compare_digest(current_owner, self.owner_hash)
                    or current_purpose != self.purpose
                    or expires_at <= now
                ):
                    raise MetaSubjectDeletionChangedError("Meta subject lease was lost")
                current_snapshot = None
                if expected_snapshot is not None:
                    current_snapshot = _capture_snapshot(self.db, self.subject_key, transaction)
                    if (
                        current_snapshot.fingerprint != expected_snapshot.fingerprint
                        or not current_snapshot.oauth_allowed_for(self.oauth_started_at)
                    ):
                        raise MetaSubjectDeletionChangedError("Meta deletion state changed during OAuth")
                transaction.set(
                    reference,
                    _lease_document(
                        owner_hash=self.owner_hash,
                        purpose=self.purpose,
                        acquired_at=self.acquired_at,
                        updated_at=now,
                        expires_at=now + self.lease_seconds,
                    ),
                )
                transaction.commit()
                return current_snapshot
            except MetaSubjectDeletionGuardError:
                raise
            except Exception as exc:
                last_error = exc
        raise MetaSubjectDeletionStoreUnavailableError("Meta subject lease verification failed") from last_error

    def renew(self) -> None:
        self._renew(expected_snapshot=None)

    def assert_oauth_snapshot_unchanged(self) -> None:
        if self.snapshot is None:
            raise MetaSubjectDeletionGuardError("Meta OAuth deletion snapshot is unavailable")
        self._renew(expected_snapshot=self.snapshot)

    def record_deauthorization(self, *, deauthorized_at: float | None = None) -> int:
        """Idempotently record the signed event time under the subject lease."""

        if self.purpose != "deauthorization":
            raise MetaSubjectDeletionGuardError("Meta subject lease purpose is invalid")
        lease_reference = _lease_ref(self.db, self.subject_key)
        deauthorization_reference = _deauthorization_ref(self.db, self.subject_key)
        last_error: Exception | None = None
        for _attempt in range(5):
            try:
                now = time.time()
                event_time = now if deauthorized_at is None else float(deauthorized_at)
                if not math.isfinite(event_time) or event_time <= 0.0 or event_time > now + 300.0:
                    raise MetaSubjectDeletionGuardError("Meta deauthorization timestamp is invalid")
                transaction = self.db.transaction()
                lease_snapshot = lease_reference.get(transaction=transaction)
                if not lease_snapshot.exists:
                    raise MetaSubjectDeletionChangedError("Meta subject lease was lost")
                current_owner, current_purpose, expires_at = _parse_lease(_snapshot_dict(lease_snapshot))
                if (
                    not hmac.compare_digest(current_owner, self.owner_hash)
                    or current_purpose != self.purpose
                    or expires_at <= now
                ):
                    raise MetaSubjectDeletionChangedError("Meta subject lease was lost")
                state_snapshot = deauthorization_reference.get(transaction=transaction)
                current: dict[str, Any] = {}
                if state_snapshot.exists:
                    current = _snapshot_dict(state_snapshot)
                    if (
                        not set(current).issubset(_DEAUTHORIZATION_SAFE_FIELDS)
                        or current.get("schema_version") != _SCHEMA_VERSION
                    ):
                        raise MetaSubjectDeletionGuardError("Meta deauthorization state is invalid")
                current_generation = int(current.get("generation") or 0)
                current_event_time = float(current.get("deauthorized_at") or 0.0)
                generation = current_generation + 1 if event_time > current_event_time else current_generation
                transaction.set(
                    deauthorization_reference,
                    {
                        "schema_version": _SCHEMA_VERSION,
                        "generation": generation,
                        "deauthorized_at": max(event_time, current_event_time),
                    },
                )
                transaction.set(
                    lease_reference,
                    _lease_document(
                        owner_hash=self.owner_hash,
                        purpose=self.purpose,
                        acquired_at=self.acquired_at,
                        updated_at=now,
                        expires_at=now + self.lease_seconds,
                    ),
                )
                transaction.commit()
                return generation
            except MetaSubjectDeletionGuardError:
                raise
            except Exception as exc:
                last_error = exc
        raise MetaSubjectDeletionStoreUnavailableError("Meta deauthorization state write failed") from last_error

    def release(self) -> bool:
        reference = _lease_ref(self.db, self.subject_key)
        last_error: Exception | None = None
        for _attempt in range(5):
            try:
                now = time.time()
                transaction = self.db.transaction()
                lease_snapshot = reference.get(transaction=transaction)
                if not lease_snapshot.exists:
                    return False
                current_owner, current_purpose, _expires_at = _parse_lease(_snapshot_dict(lease_snapshot))
                if not hmac.compare_digest(current_owner, self.owner_hash) or current_purpose != self.purpose:
                    return False
                transaction.set(
                    reference,
                    _lease_document(
                        owner_hash="",
                        purpose="released",
                        acquired_at=self.acquired_at,
                        updated_at=now,
                        expires_at=0.0,
                    ),
                )
                transaction.commit()
                return True
            except MetaSubjectDeletionGuardError:
                raise
            except Exception as exc:
                last_error = exc
        raise MetaSubjectDeletionStoreUnavailableError("Meta subject lease release failed") from last_error

    def __enter__(self) -> MetaSubjectDeletionLease:
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        # The lease is bounded, so a post-activation release outage cannot leave
        # a permanent lock. Acquisition and the immediate pre-activation check
        # remain fail-closed; release is deliberately best effort.
        try:
            self.release()
        except MetaSubjectDeletionGuardError:
            pass


def _acquire_once(
    *,
    db: Any,
    subject_key: str,
    purpose: Literal["oauth", "deletion", "deauthorization"],
    lease_seconds: float,
    capture_snapshot: bool,
    oauth_started_at: float,
) -> MetaSubjectDeletionLease:
    owner_token = secrets.token_urlsafe(32)
    owner_hash = hashlib.sha256(owner_token.encode()).hexdigest()
    reference = _lease_ref(db, subject_key)
    last_error: Exception | None = None
    for _attempt in range(5):
        try:
            now = time.time()
            transaction = db.transaction()
            lease_snapshot = reference.get(transaction=transaction)
            if lease_snapshot.exists:
                current_owner, _current_purpose, expires_at = _parse_lease(_snapshot_dict(lease_snapshot))
                if current_owner and expires_at > now:
                    raise MetaSubjectDeletionLeaseBusyError("Meta subject lease is busy")
            snapshot = _capture_snapshot(db, subject_key, transaction) if capture_snapshot else None
            transaction.set(
                reference,
                _lease_document(
                    owner_hash=owner_hash,
                    purpose=purpose,
                    acquired_at=now,
                    updated_at=now,
                    expires_at=now + lease_seconds,
                ),
            )
            transaction.commit()
            return MetaSubjectDeletionLease(
                db=db,
                subject_key=subject_key,
                owner_token=owner_token,
                purpose=purpose,
                acquired_at=now,
                lease_seconds=lease_seconds,
                snapshot=snapshot,
                oauth_started_at=oauth_started_at,
            )
        except MetaSubjectDeletionLeaseBusyError:
            raise
        except MetaSubjectDeletionGuardError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaSubjectDeletionStoreUnavailableError("Meta subject lease transaction failed") from last_error


def acquire_meta_subject_deletion_lease(
    subject_key: str,
    *,
    purpose: Literal["oauth", "deletion", "deauthorization"],
    wait_timeout_seconds: float = 0.0,
    lease_seconds: float = _DEFAULT_LEASE_SECONDS,
    capture_snapshot: bool = False,
    oauth_started_at: float = 0.0,
) -> MetaSubjectDeletionLease:
    """Acquire one bounded subject lease, optionally waiting for OAuth to finish."""

    resolved_key = str(subject_key or "").strip().lower()
    if not _SUBJECT_KEY_RE.fullmatch(resolved_key):
        raise MetaSubjectDeletionGuardError("Meta deletion subject key is invalid")
    resolved_lease_seconds = min(max(float(lease_seconds), 1.0), _DEFAULT_LEASE_SECONDS)
    wait_seconds = max(0.0, float(wait_timeout_seconds))
    deadline = time.monotonic() + wait_seconds
    db = _firestore_db()
    while True:
        try:
            return _acquire_once(
                db=db,
                subject_key=resolved_key,
                purpose=purpose,
                lease_seconds=resolved_lease_seconds,
                capture_snapshot=capture_snapshot,
                oauth_started_at=float(oauth_started_at),
            )
        except MetaSubjectDeletionLeaseBusyError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise
            time.sleep(min(0.05, remaining))


def acquire_meta_oauth_subject_guard(
    subject_key: str,
    *,
    oauth_started_at: float = 0.0,
) -> MetaSubjectDeletionLease:
    """Capture an allowed deletion snapshot and hold it through OAuth activation."""

    lease = acquire_meta_subject_deletion_lease(
        subject_key,
        purpose="oauth",
        capture_snapshot=True,
        oauth_started_at=oauth_started_at,
    )
    if lease.snapshot is None or not lease.snapshot.oauth_allowed_for(oauth_started_at):
        lease.release()
        state = lease.snapshot.state if lease.snapshot is not None else "unavailable"
        raise MetaSubjectDeletionBlockedError(f"Meta OAuth is blocked by deletion state: {state}")
    return lease


def acquire_meta_deletion_subject_guard(subject_key: str) -> MetaSubjectDeletionLease:
    """Wait briefly behind an in-flight activation, then serialize request/revoke."""

    return acquire_meta_subject_deletion_lease(
        subject_key,
        purpose="deletion",
        wait_timeout_seconds=_DEFAULT_DELETION_WAIT_SECONDS,
    )


def acquire_meta_deauthorization_subject_guard(subject_key: str) -> MetaSubjectDeletionLease:
    """Wait behind an in-flight OAuth activation, then make deauthorization win."""

    return acquire_meta_subject_deletion_lease(
        subject_key,
        purpose="deauthorization",
        wait_timeout_seconds=_DEFAULT_DELETION_WAIT_SECONDS,
    )
