"""Durable subject-boundary tests for Meta OAuth versus data deletion."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from services.meta_subject_deletion_guard import (
    MetaSubjectDeletionBlockedError,
    MetaSubjectDeletionChangedError,
    MetaSubjectDeletionStoreUnavailableError,
    acquire_meta_deauthorization_subject_guard,
    acquire_meta_deletion_subject_guard,
    acquire_meta_oauth_subject_guard,
    acquire_meta_subject_deletion_lease,
    meta_deletion_subject_hmac,
)
from tests.meta_compliance_helpers import _FakeFirestore

APP_KEY = "linas_first_party"
APP_ID = "2963733803971681"
APP_SECRET = "subject-guard-secret-tests"
META_USER_ID = "123456789"


def _subject_key() -> str:
    return meta_deletion_subject_hmac(
        app_key=APP_KEY,
        app_id=APP_ID,
        auth_flow="facebook_login",
        meta_user_id=META_USER_ID,
        app_secret=APP_SECRET,
    )


def _patch_db(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    import utils.utils

    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)


def _set_request(
    db: _FakeFirestore,
    *,
    subject_key: str,
    state: str,
    generation: int = 1,
    code: str = "a" * 32,
) -> None:
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    app.collection("meta_deletion_subject_index").document(subject_key).set(
        {"schema_version": 1, "confirmation_code": code, "created_at": 100}
    )
    app.collection("meta_deletion_requests").document(code).set(
        {
            "schema_version": 1,
            "confirmation_code": code,
            "app_key": APP_KEY,
            "app_id": APP_ID,
            "auth_flow": "facebook_login",
            "bindings": [],
            "current_bindings": [],
            "generation": generation,
            "required_nodes": ["node01", "node02"],
            "state": state,
            "coordinator_state": "completed" if state in {"completed", "no_data"} else "pending",
            "requested_at": 100,
            "updated_at": 100 + generation,
            "completed_at": 100 + generation if state in {"completed", "no_data", "failed"} else None,
            "revoked_bindings": 0,
            "shared_redacted_documents": 0,
            "redacted_ledger_documents": 0,
            "safe_error": "registry_conflict" if state == "failed" else "none",
        }
    )


def test_oauth_none_snapshot_is_owner_verified_and_pii_free(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()

    with acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=1_000.0) as guard:
        assert guard.snapshot is not None and guard.snapshot.state == "none"
        guard.assert_oauth_snapshot_unchanged()
        lease = (
            db.collection("artifacts")
            .document("linas-ai-bot-backend")
            .collection("meta_deletion_subject_leases")
            .document(subject_key)
        )
        serialized = json.dumps(lease.data, sort_keys=True)
        assert guard.owner_token not in serialized
        assert META_USER_ID not in serialized
        assert APP_SECRET not in serialized
        assert lease.data["owner_hash"] == hashlib.sha256(guard.owner_token.encode()).hexdigest()

    assert lease.data["purpose"] == "released"
    assert lease.data["owner_hash"] == ""
    assert lease.data["expires_at"] == 0.0


@pytest.mark.parametrize("state", ["pending", "failed"])
def test_oauth_blocks_pending_and_failed_deletion(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    _set_request(db, subject_key=subject_key, state=state)

    with pytest.raises(MetaSubjectDeletionBlockedError):
        acquire_meta_oauth_subject_guard(subject_key)


@pytest.mark.parametrize("state", ["completed", "no_data"])
def test_deliberate_reconnect_allows_unchanged_terminal_deletion(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    _set_request(db, subject_key=subject_key, state=state)

    with acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=1_000.0) as guard:
        assert guard.snapshot is not None and guard.snapshot.state == state
        guard.assert_oauth_snapshot_unchanged()


def test_none_to_completed_request_change_is_detected_before_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()

    with acquire_meta_oauth_subject_guard(subject_key) as guard:
        _set_request(db, subject_key=subject_key, state="completed")
        with pytest.raises(MetaSubjectDeletionChangedError):
            guard.assert_oauth_snapshot_unchanged()


def test_completed_request_generation_change_is_detected_before_activation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    _set_request(db, subject_key=subject_key, state="completed", generation=1)

    with acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=1_000.0) as guard:
        _set_request(db, subject_key=subject_key, state="completed", generation=2)
        with pytest.raises(MetaSubjectDeletionChangedError):
            guard.assert_oauth_snapshot_unchanged()


@pytest.mark.parametrize("state", ["completed", "no_data"])
def test_oauth_started_before_terminal_deletion_cannot_resurrect_authorization(
    monkeypatch: pytest.MonkeyPatch,
    state: str,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    _set_request(db, subject_key=subject_key, state=state)

    with pytest.raises(MetaSubjectDeletionBlockedError):
        acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=99.0)


def test_deletion_waits_behind_activation_then_acquires_same_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    oauth_guard = acquire_meta_oauth_subject_guard(subject_key)
    started = threading.Event()
    acquired = threading.Event()

    def acquire_deletion() -> None:
        started.set()
        with acquire_meta_deletion_subject_guard(subject_key):
            acquired.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        waiter = pool.submit(acquire_deletion)
        assert started.wait(timeout=2)
        time.sleep(0.08)
        assert acquired.is_set() is False
        oauth_guard.release()
        waiter.result(timeout=2)
    assert acquired.is_set() is True


def test_deauthorization_after_flow_start_blocks_that_oauth_but_new_reconnect_is_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    old_flow_started_at = time.time() - 10

    with acquire_meta_deauthorization_subject_guard(subject_key) as guard:
        assert guard.record_deauthorization() == 1
    deauthorized_at = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_deauthorization_subjects")
        .document(subject_key)
        .data["deauthorized_at"]
    )

    with pytest.raises(MetaSubjectDeletionBlockedError):
        acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=old_flow_started_at)
    with acquire_meta_oauth_subject_guard(
        subject_key,
        oauth_started_at=float(deauthorized_at) + 1,
    ) as oauth_guard:
        oauth_guard.assert_oauth_snapshot_unchanged()


def test_delayed_deauthorization_retry_keeps_original_signed_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()

    with acquire_meta_deauthorization_subject_guard(subject_key) as guard:
        assert guard.record_deauthorization(deauthorized_at=100.0) == 1
    with acquire_meta_deauthorization_subject_guard(subject_key) as guard:
        assert guard.record_deauthorization(deauthorized_at=100.0) == 1

    state = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_deauthorization_subjects")
        .document(subject_key)
        .data
    )
    assert state == {"schema_version": 1, "generation": 1, "deauthorized_at": 100.0}


def test_deauthorization_waits_for_inflight_oauth_then_tombstone_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    flow_started_at = time.time() - 1
    oauth_guard = acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=flow_started_at)
    acquired = threading.Event()

    def deauthorize() -> None:
        with acquire_meta_deauthorization_subject_guard(subject_key) as guard:
            guard.record_deauthorization()
            acquired.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        waiter = pool.submit(deauthorize)
        time.sleep(0.08)
        assert acquired.is_set() is False
        oauth_guard.release()
        waiter.result(timeout=2)

    assert acquired.is_set() is True
    with pytest.raises(MetaSubjectDeletionBlockedError):
        acquire_meta_oauth_subject_guard(subject_key, oauth_started_at=flow_started_at)


def test_stolen_owner_cannot_renew_or_release_new_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    original = acquire_meta_subject_deletion_lease(subject_key, purpose="oauth", capture_snapshot=True)
    lease = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_deletion_subject_leases")
        .document(subject_key)
    )
    replacement_hash = "b" * 64
    lease.set(
        {
            "schema_version": 1,
            "owner_hash": replacement_hash,
            "purpose": "deletion",
            "acquired_at": time.time(),
            "updated_at": time.time(),
            "expires_at": time.time() + 60,
        }
    )

    with pytest.raises(MetaSubjectDeletionChangedError):
        original.assert_oauth_snapshot_unchanged()
    assert original.release() is False
    assert lease.data["owner_hash"] == replacement_hash


def test_expired_lease_is_replaced_and_old_owner_cannot_release_new_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _FakeFirestore()
    _patch_db(monkeypatch, db)
    subject_key = _subject_key()
    original = acquire_meta_subject_deletion_lease(subject_key, purpose="oauth", capture_snapshot=True)
    lease = (
        db.collection("artifacts")
        .document("linas-ai-bot-backend")
        .collection("meta_deletion_subject_leases")
        .document(subject_key)
    )
    lease.update({"expires_at": time.time() - 1})

    replacement = acquire_meta_subject_deletion_lease(subject_key, purpose="deletion")

    assert replacement.owner_hash != original.owner_hash
    assert original.release() is False
    assert lease.data["owner_hash"] == replacement.owner_hash
    assert replacement.release() is True


def test_guard_fails_closed_without_firestore(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_db(monkeypatch, None)
    with pytest.raises(MetaSubjectDeletionStoreUnavailableError, match="unavailable"):
        acquire_meta_oauth_subject_guard(_subject_key())
