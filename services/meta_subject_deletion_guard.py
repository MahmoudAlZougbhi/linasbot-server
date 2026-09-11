"""Firestore subject lease that serializes Meta OAuth with data deletion."""

from __future__ import annotations

import hashlib
import hmac
import math
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_subject_deletion_guard_models import (
    _DEAUTHORIZATION_SAFE_FIELDS,
    _DEFAULT_DELETION_WAIT_SECONDS,
    _DEFAULT_LEASE_SECONDS,
    _SCHEMA_VERSION,
    _SUBJECT_KEY_RE,
    MetaSubjectDeletionBlockedError,
    MetaSubjectDeletionChangedError,
    MetaSubjectDeletionGuardError,
    MetaSubjectDeletionLeaseBusyError,
    MetaSubjectDeletionSnapshot,
    MetaSubjectDeletionStoreUnavailableError,
    meta_deletion_subject_hmac,
)
from services.meta_subject_deletion_guard_store import (
    _capture_snapshot,
    _deauthorization_ref,
    _firestore_db,
    _lease_document,
    _lease_ref,
    _parse_lease,
    _snapshot_dict,
)

__all__ = [
    "MetaSubjectDeletionBlockedError",
    "MetaSubjectDeletionChangedError",
    "MetaSubjectDeletionGuardError",
    "MetaSubjectDeletionLease",
    "MetaSubjectDeletionLeaseBusyError",
    "MetaSubjectDeletionSnapshot",
    "MetaSubjectDeletionStoreUnavailableError",
    "acquire_meta_deauthorization_subject_guard",
    "acquire_meta_deletion_subject_guard",
    "acquire_meta_oauth_subject_guard",
    "acquire_meta_subject_deletion_lease",
    "meta_deletion_subject_hmac",
]


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

                def _verify(transaction: Any, now: float = now) -> MetaSubjectDeletionSnapshot | None:
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
                    return current_snapshot

                return run_firestore_transaction(self.db, _verify)
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

                def _record(transaction: Any, now: float = now, event_time: float = event_time) -> int:
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
                    return generation

                return run_firestore_transaction(self.db, _record)
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

                def _release(transaction: Any, now: float = now) -> bool:
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
                    return True

                return run_firestore_transaction(self.db, _release)
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
    """Acquire one live lease, recovering only this attempt's owner after ACK loss.

    Inner retries reuse ``owner_token``. If Firestore committed and the ACK was
    lost, the same owner and purpose may overwrite that row. A later acquire
    mints a new owner, so a zombie lease still returns busy until expiry
    (~300s). Do not steal another live owner of the same purpose: concurrent
    OAuth and deletion must stay serialized. Busy is therefore not fully fixed
    for a second Connect after ACK-loss.
    """

    owner_token = secrets.token_urlsafe(32)
    owner_hash = hashlib.sha256(owner_token.encode()).hexdigest()
    reference = _lease_ref(db, subject_key)
    last_error: Exception | None = None
    for _attempt in range(5):
        try:
            now = time.time()

            def _acquire(transaction: Any, now: float = now) -> MetaSubjectDeletionSnapshot | None:
                lease_snapshot = reference.get(transaction=transaction)
                if lease_snapshot.exists:
                    current_owner, current_purpose, expires_at = _parse_lease(_snapshot_dict(lease_snapshot))
                    if current_owner and expires_at > now:
                        # Inner commit/ACK retries reuse this token. Recover that owner and
                        # purpose only. A different live owner still waits until expiry.
                        if not hmac.compare_digest(current_owner, owner_hash) or current_purpose != purpose:
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
                return snapshot

            snapshot = run_firestore_transaction(db, _acquire)
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
        raise MetaSubjectDeletionBlockedError(state)
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
