"""Process pending Meta deletion requests and run locked coordinator work."""

from __future__ import annotations

import fcntl
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_app_registry_common import AuthFlow
from services.meta_data_deletion_store import (
    _binding_scopes,
    _finalize_shared_request,
    _get_or_create_shared_request,
    _mark_coordinator_completed,
    _mark_coordinator_failed,
    _parse_shared_request,
    _read_shared_request,
    _snapshot_payload,
)
from services.meta_data_deletion_types import (
    _CONFIRMATION_CODE_RE,
    _META_USER_ID_RE,
    _REQUEST_COLLECTION,
    _SCHEMA_VERSION,
    MetaDeletionResult,
    MetaDeletionStateError,
    MetaDeletionStoreUnavailableError,
    _app_document,
    _deletion_node_config,
    _firestore_db,
    _request_ref,
    _SharedDeletionRequest,
    _subject_index_key,
)
from storage.persistent_storage import _DATA_ROOT

_LOCK_DIR = Path(_DATA_ROOT) / "meta_deletion_runtime"
_DELETION_THREAD_LOCK = threading.RLock()


def _resolved_lock_dir() -> Path:
    """Honor tests that patch ``services.meta_data_deletion._LOCK_DIR``."""

    from services import meta_data_deletion as facade

    return facade._LOCK_DIR


@contextmanager
def _deletion_process_lock() -> Iterator[None]:
    """Serialize callback work within one node; Firestore serializes the cluster."""

    lock_dir = _resolved_lock_dir()
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(lock_dir, 0o700)
    lock_path = lock_dir / ".deletion.lock"
    with _DELETION_THREAD_LOCK:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _redaction_has_remaining(stats: dict[str, int | bool], *, shared: bool) -> bool:
    key = "firestore_changed" if shared else "local_changed"
    return int(stats.get(key) or 0) > 0


def _sanitize_local_and_ack(db: Any, request: _SharedDeletionRequest) -> tuple[_SharedDeletionRequest, int]:
    from services.meta_claim_data_deletion import delete_and_verify_local_meta_claims
    from services.meta_inbound_deletion_fence import install_local_inbound_binding_deletion_fences
    from services.meta_inbound_retention import (
        inbound_redaction_has_blockers,
        redact_local_inbound_events_for_bindings,
    )

    node_id, configured_nodes = _deletion_node_config()
    if configured_nodes != request.required_nodes or node_id not in request.required_nodes:
        raise MetaDeletionStateError("Meta deletion node configuration does not match the request")
    if request.state in {"completed", "no_data"}:
        return request, 0
    if request.state != "pending" or request.coordinator_state != "completed":
        raise MetaDeletionStateError("Meta deletion request is not ready for node sanitation")
    binding_ids = {item.binding_id for item in request.bindings}
    install_local_inbound_binding_deletion_fences(binding_ids)
    preflight = redact_local_inbound_events_for_bindings(binding_ids, apply=False)
    # Orphan atomic temp files are blockers for acknowledgement, but they are
    # safe for the apply phase to remove while holding the ledger lock.
    preflight_without_removable_orphans = {**preflight, "local_orphan_files": 0}
    if inbound_redaction_has_blockers(preflight_without_removable_orphans, require_firestore=False):
        raise RuntimeError("Local inbound events are not ready for deletion")
    claim_stats = delete_and_verify_local_meta_claims(binding_ids)
    if int(claim_stats.get("errors") or 0) or int(claim_stats.get("remaining") or 0):
        raise RuntimeError("Local Meta claim deletion did not complete")
    applied = redact_local_inbound_events_for_bindings(binding_ids, apply=True)
    if inbound_redaction_has_blockers(applied, require_firestore=False):
        raise RuntimeError("Local inbound event redaction did not complete")
    verify = redact_local_inbound_events_for_bindings(binding_ids, apply=False)
    if inbound_redaction_has_blockers(verify, require_firestore=False) or _redaction_has_remaining(
        verify,
        shared=False,
    ):
        raise RuntimeError("Local inbound event redaction verification failed")
    # Use the verified matching total, not the mutation count. A retry after an
    # ambiguous ack commit must publish the same aggregate instead of replacing
    # an earlier non-zero count with zero after the files are already redacted.
    local_redacted = int(verify.get("local_matched") or 0)

    request_ref = _request_ref(db, request.confirmation_code)
    ack_ref = request_ref.collection("node_acks").document(node_id)
    try:

        def _acknowledge(transaction: Any) -> None:
            current = _parse_shared_request(
                _snapshot_payload(request_ref.get(transaction=transaction), label="request"),
                request.confirmation_code,
            )
            if (
                current.generation != request.generation
                or current.state != "pending"
                or current.coordinator_state != "completed"
                or node_id not in current.required_nodes
            ):
                raise MetaDeletionStateError("Meta deletion request changed before node acknowledgement")
            transaction.set(
                ack_ref,
                {
                    "schema_version": _SCHEMA_VERSION,
                    "node_id": node_id,
                    "status": "completed",
                    "request_generation": current.generation,
                    "acknowledged_at": int(time.time()),
                    "local_redacted_documents": local_redacted,
                    "local_blockers": 0,
                    "local_remaining_changes": 0,
                },
            )

        run_firestore_transaction(db, _acknowledge)
    except MetaDeletionStateError:
        raise
    except Exception as exc:
        raise MetaDeletionStoreUnavailableError("Meta deletion node acknowledgement failed") from exc
    return _finalize_shared_request(db, request.confirmation_code), local_redacted


def read_deletion_status(confirmation_code: str) -> dict[str, Any] | None:
    """Read only the shared HA status; storage failures never look like unknown codes."""

    code = str(confirmation_code or "").strip().lower()
    if not _CONFIRMATION_CODE_RE.fullmatch(code):
        return None
    request = _read_shared_request(_firestore_db(), code)
    if request is None:
        return None
    status: dict[str, Any] = {
        "confirmation_code": request.confirmation_code,
        "status": request.state,
        "requested_at": request.requested_at,
        "revoked_bindings": request.revoked_bindings,
        "redacted_ledger_documents": request.redacted_ledger_documents,
    }
    if request.completed_at is not None:
        status["completed_at"] = request.completed_at
    return status


def process_pending_meta_deletion_requests() -> dict[str, int]:
    """Run on every node so each private ledger contributes its own current ack."""

    node_id, configured_nodes = _deletion_node_config()
    db = _firestore_db()
    try:
        snapshots = list(_app_document(db).collection(_REQUEST_COLLECTION).stream())
    except Exception as exc:
        raise MetaDeletionStoreUnavailableError("Meta deletion request scan failed") from exc
    stats = {"examined": 0, "acknowledged": 0, "completed": 0, "pending": 0, "errors": 0}
    for snapshot in snapshots:
        try:
            code = str(getattr(snapshot.reference, "path", "")).rsplit("/", 1)[-1]
            request = _parse_shared_request(_snapshot_payload(snapshot, label="request"), code)
            if request.required_nodes != configured_nodes or node_id not in request.required_nodes:
                raise MetaDeletionStateError("Meta deletion node configuration does not match the request")
            if request.state in {"completed", "no_data"}:
                continue
            stats["examined"] += 1
            if request.state != "pending" or request.coordinator_state != "completed":
                stats["pending"] += 1
                continue
            finalized, _local_redacted = _sanitize_local_and_ack(db, request)
            stats["acknowledged"] += 1
            if finalized.state in {"completed", "no_data"}:
                stats["completed"] += 1
            else:
                stats["pending"] += 1
        except Exception:
            stats["errors"] += 1
    return stats


def delete_meta_social_user_data(
    meta_user_id: str,
    app_secret: str,
    *,
    app_key: str,
    signing_app_id: str,
    auth_flow: AuthFlow,
    registry: Any | None = None,
) -> MetaDeletionResult:
    with _deletion_process_lock():
        return _delete_meta_social_user_data_locked(
            meta_user_id,
            app_secret,
            app_key=app_key,
            signing_app_id=signing_app_id,
            auth_flow=auth_flow,
            registry=registry,
        )


def _delete_meta_social_user_data_locked(
    meta_user_id: str,
    app_secret: str,
    *,
    app_key: str,
    signing_app_id: str,
    auth_flow: AuthFlow,
    registry: Any | None,
) -> MetaDeletionResult:
    """Coordinate shared deletion, then ack only this node's verified local ledger."""

    raw_user_id = str(meta_user_id or "").strip()
    if not _META_USER_ID_RE.fullmatch(raw_user_id):
        raise ValueError("Invalid Meta user identifier")
    signing_secret = str(app_secret or "").strip()
    if not signing_secret:
        raise ValueError("App secret is required")
    signing_id = str(signing_app_id or "").strip()
    if not signing_id.isdigit():
        raise ValueError("Signing App ID is required")
    if auth_flow not in {"facebook_login", "instagram_login"}:
        raise ValueError("Meta authorization flow is invalid")

    from services.meta_app_registry import get_meta_app_registry
    from services.meta_claim_data_deletion import (
        apply_shared_meta_claim_deletion_plan,
        build_shared_meta_claim_deletion_plan,
    )
    from services.meta_inbound_deletion_fence import install_inbound_binding_deletion_fences
    from services.meta_inbound_retention import (
        inbound_redaction_has_blockers,
        redact_shared_inbound_events_for_bindings,
    )
    from services.meta_subject_deletion_guard import (
        MetaSubjectDeletionGuardError,
        acquire_meta_deletion_subject_guard,
    )

    _node_id, required_nodes = _deletion_node_config()
    db = _firestore_db()
    current_registry = registry or get_meta_app_registry()
    subject_key = _subject_index_key(app_key, signing_id, auth_flow, raw_user_id, signing_secret)
    revoked_this_call = 0
    shared_redacted_this_call = 0
    try:
        with acquire_meta_deletion_subject_guard(subject_key) as subject_guard:
            # The registry scope is read only after the subject lease is owned;
            # otherwise an OAuth activation could land between this read and
            # request creation and escape exact revocation.
            current_bindings = current_registry.find_authorization_bindings(
                app_key=app_key,
                auth_flow=auth_flow,
                authorized_meta_user_id=raw_user_id,
            )
            scopes = _binding_scopes(current_bindings)
            subject_guard.renew()
            request = _get_or_create_shared_request(
                db=db,
                subject_key=subject_key,
                app_key=app_key,
                app_id=signing_id,
                auth_flow=auth_flow,
                bindings=scopes,
                required_nodes=required_nodes,
            )
            if request.state in {"completed", "no_data"}:
                return MetaDeletionResult(
                    confirmation_code=request.confirmation_code,
                    deleted_user_documents=0,
                    deleted_nested_documents=0,
                    deleted_index_documents=0,
                )

            if request.coordinator_state != "completed":
                binding_ids = {item.binding_id for item in request.bindings}
                expected_generations = {item.binding_id: item.expected_generation for item in request.current_bindings}
                install_inbound_binding_deletion_fences(binding_ids)
                preflight = redact_shared_inbound_events_for_bindings(binding_ids, apply=False)
                if inbound_redaction_has_blockers(preflight, require_firestore=True):
                    _mark_coordinator_failed(db, request, safe_error="shared_preflight")
                    raise RuntimeError("Shared inbound events are not ready for deletion")
                try:
                    claim_deletion_plan = build_shared_meta_claim_deletion_plan(db, binding_ids)
                except Exception:
                    _mark_coordinator_failed(db, request, safe_error="shared_preflight")
                    raise
                try:
                    # Renew immediately before exact revocation.  Request creation
                    # already makes OAuth fail closed if a very long scan outlives
                    # the bounded lease, while this check prevents a stale owner
                    # from revoking across a replacement lease.
                    subject_guard.renew()
                    revoke_exact = current_registry.revoke_authorization_exact
                    revoked = revoke_exact(
                        app_key=app_key,
                        auth_flow=auth_flow,
                        authorized_meta_user_id=raw_user_id,
                        expected_bindings=expected_generations,
                        actor_id="meta-data-deletion",
                    )
                except MetaSubjectDeletionGuardError:
                    raise
                except Exception:
                    _mark_coordinator_failed(db, request, safe_error="registry_conflict")
                    raise
                revoked_this_call = len(revoked)
                try:
                    claim_stats = apply_shared_meta_claim_deletion_plan(db, claim_deletion_plan)
                    if int(claim_stats.get("errors") or 0) or int(claim_stats.get("remaining") or 0):
                        raise RuntimeError("Shared Meta claim deletion did not complete")
                    # Re-scan to a fixed point while the binding fence prevents
                    # new Meta claim reservations. This also catches a legacy
                    # worker that crossed the first scan before seeing the fence.
                    for _claim_pass in range(3):
                        residual_plan = build_shared_meta_claim_deletion_plan(db, binding_ids)
                        if not residual_plan.shared_documents:
                            break
                        residual_stats = apply_shared_meta_claim_deletion_plan(db, residual_plan)
                        if int(residual_stats.get("errors") or 0) or int(residual_stats.get("remaining") or 0):
                            raise RuntimeError("Shared Meta claim deletion did not converge")
                    else:
                        raise RuntimeError("Shared Meta claim deletion did not reach a fixed point")
                except Exception:
                    _mark_coordinator_failed(db, request, safe_error="shared_redaction")
                    raise
                applied = redact_shared_inbound_events_for_bindings(binding_ids, apply=True)
                if inbound_redaction_has_blockers(applied, require_firestore=True):
                    _mark_coordinator_failed(db, request, safe_error="shared_redaction")
                    raise RuntimeError("Shared inbound event redaction did not complete")
                verify = redact_shared_inbound_events_for_bindings(binding_ids, apply=False)
                if inbound_redaction_has_blockers(verify, require_firestore=True) or _redaction_has_remaining(
                    verify,
                    shared=True,
                ):
                    _mark_coordinator_failed(db, request, safe_error="shared_redaction")
                    raise RuntimeError("Shared inbound event redaction verification failed")
                # The verified match total is stable across concurrent coordinators
                # and ambiguous retries, unlike a per-attempt mutation count.
                shared_redacted_this_call = int(verify.get("firestore_matched") or 0)
                post_revoke_bindings = current_registry.find_authorization_bindings(
                    app_key=app_key,
                    auth_flow=auth_flow,
                    authorized_meta_user_id=raw_user_id,
                )
                post_revoke_scopes = _binding_scopes(post_revoke_bindings)
                if {item.binding_id for item in post_revoke_scopes} != set(expected_generations):
                    _mark_coordinator_failed(db, request, safe_error="registry_conflict")
                    raise MetaDeletionStateError("Meta deletion registry scope changed after revocation")
                request = _mark_coordinator_completed(
                    db,
                    request,
                    revoked_bindings=len(request.current_bindings),
                    shared_redacted_documents=shared_redacted_this_call,
                    current_bindings=post_revoke_scopes,
                )
    except MetaSubjectDeletionGuardError as exc:
        raise MetaDeletionStoreUnavailableError("Meta deletion subject guard is unavailable") from exc

    local_redacted_this_call = 0
    try:
        request, local_redacted_this_call = _sanitize_local_and_ack(db, request)
    except Exception:
        # The shared status remains pending and this node's scheduler retries.
        pass
    return MetaDeletionResult(
        confirmation_code=request.confirmation_code,
        deleted_user_documents=0,
        deleted_nested_documents=0,
        deleted_index_documents=0,
        revoked_bindings=revoked_this_call,
        redacted_ledger_documents=shared_redacted_this_call + local_redacted_this_call,
    )
