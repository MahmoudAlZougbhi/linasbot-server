"""Verification and deletion helpers for Meta's user-data deletion callback."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_app_registry_common import AuthFlow
from storage.persistent_storage import _DATA_ROOT

_META_USER_ID_RE = re.compile(r"^[0-9]{3,64}$")
_CONFIRMATION_CODE_RE = re.compile(r"^[0-9a-f]{32}$")
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BINDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_MAX_SIGNED_REQUEST_AGE_SECONDS = 7 * 24 * 60 * 60
_MAX_FUTURE_SKEW_SECONDS = 5 * 60
_LOCK_DIR = Path(_DATA_ROOT) / "meta_deletion_runtime"
_FIRESTORE_APP_ID = "linas-ai-bot-backend"
_SUBJECT_INDEX_COLLECTION = "meta_deletion_subject_index"
_REQUEST_COLLECTION = "meta_deletion_requests"
_SCHEMA_VERSION = 1
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
_INDEX_SAFE_FIELDS = frozenset({"schema_version", "confirmation_code", "created_at"})
_ACK_SAFE_FIELDS = frozenset(
    {
        "schema_version",
        "node_id",
        "status",
        "request_generation",
        "acknowledged_at",
        "local_redacted_documents",
        "local_blockers",
        "local_remaining_changes",
    }
)
_DELETION_THREAD_LOCK = threading.RLock()


@dataclass(frozen=True)
class VerifiedMetaDeletionRequest:
    meta_user_id: str
    issued_at: int


@dataclass(frozen=True)
class MetaDeletionResult:
    confirmation_code: str
    deleted_user_documents: int
    deleted_nested_documents: int
    deleted_index_documents: int
    revoked_bindings: int = 0
    redacted_ledger_documents: int = 0


@dataclass(frozen=True)
class _DeletionBindingScope:
    binding_id: str
    expected_generation: int


@dataclass(frozen=True)
class _SharedDeletionRequest:
    confirmation_code: str
    app_key: str
    app_id: str
    auth_flow: AuthFlow
    # Historical union used only to redact every event ever in this request.
    bindings: tuple[_DeletionBindingScope, ...]
    # Exact current registry snapshot used for generation-bound revocation.
    current_bindings: tuple[_DeletionBindingScope, ...]
    generation: int
    required_nodes: tuple[str, ...]
    state: Literal["pending", "completed", "no_data", "failed"]
    coordinator_state: Literal["pending", "completed"]
    requested_at: int
    updated_at: int
    completed_at: int | None
    revoked_bindings: int
    shared_redacted_documents: int
    redacted_ledger_documents: int
    safe_error: str


class MetaSignedRequestError(ValueError):
    """Raised when Meta's signed_request is malformed, stale, or unauthentic."""


class MetaDeletionStoreUnavailableError(RuntimeError):
    """Raised when the authoritative Firestore deletion store cannot be used."""


class MetaDeletionStateError(RuntimeError):
    """Raised when shared deletion state is malformed, stale, or inconsistent."""


@contextmanager
def _deletion_process_lock() -> Iterator[None]:
    """Serialize callback work within one node; Firestore serializes the cluster."""

    _LOCK_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(_LOCK_DIR, 0o700)
    lock_path = _LOCK_DIR / ".deletion.lock"
    with _DELETION_THREAD_LOCK:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode((value + padding).encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise MetaSignedRequestError("Malformed signed request") from exc


def verify_meta_deletion_signed_request(
    signed_request: str,
    app_secret: str,
    *,
    now: int | None = None,
) -> VerifiedMetaDeletionRequest:
    """Verify Meta's HMAC-SHA256 signed_request without logging its contents."""
    raw = str(signed_request or "").strip()
    secret = str(app_secret or "").strip()
    if not raw or not secret or raw.count(".") != 1:
        raise MetaSignedRequestError("Invalid signed request")

    encoded_signature, encoded_payload = raw.split(".", 1)
    received_signature = _decode_base64url(encoded_signature)
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(received_signature, expected_signature):
        raise MetaSignedRequestError("Invalid signed request signature")

    try:
        decoded = json.loads(_decode_base64url(encoded_payload))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MetaSignedRequestError("Invalid signed request payload") from exc
    if not isinstance(decoded, dict):
        raise MetaSignedRequestError("Invalid signed request payload")
    payload = cast(dict[str, Any], decoded)

    algorithm = str(payload.get("algorithm") or "").strip().upper()
    if algorithm != "HMAC-SHA256":
        raise MetaSignedRequestError("Unsupported signed request algorithm")
    meta_user_id = str(payload.get("user_id") or "").strip()
    if not _META_USER_ID_RE.fullmatch(meta_user_id):
        raise MetaSignedRequestError("Invalid Meta user identifier")
    issued_at_raw = payload.get("issued_at")
    if isinstance(issued_at_raw, bool) or not isinstance(issued_at_raw, (int, str)):
        raise MetaSignedRequestError("Invalid signed request timestamp")
    try:
        issued_at = int(issued_at_raw)
    except (TypeError, ValueError) as exc:
        raise MetaSignedRequestError("Invalid signed request timestamp") from exc

    current = int(time.time()) if now is None else int(now)
    if issued_at > current + _MAX_FUTURE_SKEW_SECONDS:
        raise MetaSignedRequestError("Signed request timestamp is in the future")
    if current - issued_at > _MAX_SIGNED_REQUEST_AGE_SECONDS:
        raise MetaSignedRequestError("Signed request has expired")
    return VerifiedMetaDeletionRequest(meta_user_id=meta_user_id, issued_at=issued_at)


def generate_opaque_confirmation_code() -> str:
    """Return a random 32-character hex code that does not embed user identifiers."""
    return secrets.token_hex(16)


def deletion_confirmation_code(meta_user_id: str, app_secret: str) -> str:
    """Legacy deterministic helper retained for unit tests only."""
    if not _META_USER_ID_RE.fullmatch(str(meta_user_id or "").strip()):
        raise ValueError("Invalid Meta user identifier")
    digest = hmac.new(
        app_secret.encode("utf-8"),
        f"meta-data-deletion:{meta_user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest[:32]


def _subject_index_key(
    app_key: str,
    signing_app_id: str,
    auth_flow: AuthFlow,
    meta_user_id: str,
    app_secret: str,
) -> str:
    """Return a secret-keyed subject lookup that cannot reveal the Meta user ID."""

    from services.meta_subject_deletion_guard import meta_deletion_subject_hmac

    return meta_deletion_subject_hmac(
        app_key=app_key,
        app_id=signing_app_id,
        auth_flow=auth_flow,
        meta_user_id=meta_user_id,
        app_secret=app_secret,
    )


def _deletion_node_config() -> tuple[str, tuple[str, ...]]:
    node_id = (os.getenv("META_DELETION_NODE_ID") or "").strip()
    raw_required = (os.getenv("META_DELETION_REQUIRED_NODES") or "").strip()
    required = tuple(part.strip() for part in raw_required.split(",") if part.strip())
    if not _NODE_ID_RE.fullmatch(node_id):
        raise MetaDeletionStateError("Meta deletion node identity is not configured")
    if not required or len(required) != len(set(required)):
        raise MetaDeletionStateError("Meta deletion required nodes are not configured")
    if any(not _NODE_ID_RE.fullmatch(value) for value in required) or node_id not in required:
        raise MetaDeletionStateError("Meta deletion node configuration is invalid")
    return node_id, tuple(sorted(required))


def _firestore_db() -> Any:
    try:
        from utils.utils import get_firestore_db

        db = get_firestore_db()
    except Exception as exc:
        raise MetaDeletionStoreUnavailableError("Meta deletion store is unavailable") from exc
    if db is None:
        raise MetaDeletionStoreUnavailableError("Meta deletion store is unavailable")
    return db


def _app_document(db: Any) -> Any:
    return db.collection("artifacts").document(_FIRESTORE_APP_ID)


def _subject_index_ref(db: Any, subject_key: str) -> Any:
    return _app_document(db).collection(_SUBJECT_INDEX_COLLECTION).document(subject_key)


def _request_ref(db: Any, confirmation_code: str) -> Any:
    return _app_document(db).collection(_REQUEST_COLLECTION).document(confirmation_code)


def _safe_int(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        raise MetaDeletionStateError(f"Meta deletion {field} is invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MetaDeletionStateError(f"Meta deletion {field} is invalid") from exc
    if parsed < minimum:
        raise MetaDeletionStateError(f"Meta deletion {field} is invalid")
    return parsed


def _parse_binding_scopes(value: object) -> tuple[_DeletionBindingScope, ...]:
    if not isinstance(value, list):
        raise MetaDeletionStateError("Meta deletion binding scope is invalid")
    scopes: list[_DeletionBindingScope] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise MetaDeletionStateError("Meta deletion binding scope is invalid")
        if not set(item).issubset({"binding_id", "expected_generation"}):
            raise MetaDeletionStateError("Meta deletion binding scope contains unsafe fields")
        binding_id = str(item.get("binding_id") or "").strip()
        if not _BINDING_ID_RE.fullmatch(binding_id) or binding_id in seen:
            raise MetaDeletionStateError("Meta deletion binding scope is invalid")
        generation = _safe_int(item.get("expected_generation"), field="binding generation", minimum=1)
        seen.add(binding_id)
        scopes.append(_DeletionBindingScope(binding_id=binding_id, expected_generation=generation))
    return tuple(sorted(scopes, key=lambda item: item.binding_id))


def _parse_shared_request(value: object, confirmation_code: str) -> _SharedDeletionRequest:
    if not isinstance(value, dict):
        raise MetaDeletionStateError("Meta deletion request is invalid")
    if not set(value).issubset(_REQUEST_SAFE_FIELDS):
        raise MetaDeletionStateError("Meta deletion request contains unsafe fields")
    code = str(value.get("confirmation_code") or "").strip().lower()
    if code != confirmation_code or not _CONFIRMATION_CODE_RE.fullmatch(code):
        raise MetaDeletionStateError("Meta deletion request is invalid")
    if _safe_int(value.get("schema_version"), field="schema version", minimum=1) != _SCHEMA_VERSION:
        raise MetaDeletionStateError("Meta deletion schema version is unsupported")
    app_key = str(value.get("app_key") or "").strip()
    app_id = str(value.get("app_id") or "").strip()
    auth_flow = str(value.get("auth_flow") or "").strip()
    if not app_key or len(app_key) > 64 or not app_id.isdigit():
        raise MetaDeletionStateError("Meta deletion signing domain is invalid")
    if auth_flow not in {"facebook_login", "instagram_login"}:
        raise MetaDeletionStateError("Meta deletion signing domain is invalid")
    required_raw = value.get("required_nodes")
    if not isinstance(required_raw, list):
        raise MetaDeletionStateError("Meta deletion required nodes are invalid")
    required = tuple(sorted(str(item).strip() for item in required_raw))
    if not required or len(required) != len(set(required)) or any(not _NODE_ID_RE.fullmatch(item) for item in required):
        raise MetaDeletionStateError("Meta deletion required nodes are invalid")
    state = str(value.get("state") or "").strip()
    coordinator_state = str(value.get("coordinator_state") or "").strip()
    if state not in {"pending", "completed", "no_data", "failed"}:
        raise MetaDeletionStateError("Meta deletion status is invalid")
    if coordinator_state not in {"pending", "completed"}:
        raise MetaDeletionStateError("Meta deletion coordinator status is invalid")
    completed_at_raw = value.get("completed_at")
    completed_at = None if completed_at_raw is None else _safe_int(completed_at_raw, field="completion time")
    safe_error = str(value.get("safe_error") or "none").strip()
    if safe_error not in {"none", "shared_preflight", "registry_conflict", "shared_redaction", "internal"}:
        raise MetaDeletionStateError("Meta deletion safe error is invalid")
    return _SharedDeletionRequest(
        confirmation_code=code,
        app_key=app_key,
        app_id=app_id,
        auth_flow=auth_flow,  # type: ignore[arg-type]
        bindings=_parse_binding_scopes(value.get("bindings")),
        current_bindings=_parse_binding_scopes(value.get("current_bindings")),
        generation=_safe_int(value.get("generation"), field="request generation", minimum=1),
        required_nodes=required,
        state=state,  # type: ignore[arg-type]
        coordinator_state=coordinator_state,  # type: ignore[arg-type]
        requested_at=_safe_int(value.get("requested_at"), field="request time"),
        updated_at=_safe_int(value.get("updated_at"), field="update time"),
        completed_at=completed_at,
        revoked_bindings=_safe_int(value.get("revoked_bindings") or 0, field="revoked count"),
        shared_redacted_documents=_safe_int(
            value.get("shared_redacted_documents") or 0,
            field="shared redaction count",
        ),
        redacted_ledger_documents=_safe_int(
            value.get("redacted_ledger_documents") or 0,
            field="redaction count",
        ),
        safe_error=safe_error,
    )


def _request_payload(request: _SharedDeletionRequest) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "confirmation_code": request.confirmation_code,
        "app_key": request.app_key,
        "app_id": request.app_id,
        "auth_flow": request.auth_flow,
        "bindings": [
            {"binding_id": item.binding_id, "expected_generation": item.expected_generation}
            for item in request.bindings
        ],
        "current_bindings": [
            {"binding_id": item.binding_id, "expected_generation": item.expected_generation}
            for item in request.current_bindings
        ],
        "generation": request.generation,
        "required_nodes": list(request.required_nodes),
        "state": request.state,
        "coordinator_state": request.coordinator_state,
        "requested_at": request.requested_at,
        "updated_at": request.updated_at,
        "revoked_bindings": request.revoked_bindings,
        "shared_redacted_documents": request.shared_redacted_documents,
        "redacted_ledger_documents": request.redacted_ledger_documents,
        "safe_error": request.safe_error,
    }
    if request.completed_at is not None:
        payload["completed_at"] = request.completed_at
    return payload


def _snapshot_payload(snapshot: Any, *, label: str) -> dict[str, Any]:
    if not getattr(snapshot, "exists", False):
        raise MetaDeletionStateError(f"Meta deletion {label} is unavailable")
    try:
        payload = snapshot.to_dict()
    except Exception as exc:
        raise MetaDeletionStateError(f"Meta deletion {label} is invalid") from exc
    if not isinstance(payload, dict):
        raise MetaDeletionStateError(f"Meta deletion {label} is invalid")
    return payload


def _binding_scopes(bindings: list[Any]) -> tuple[_DeletionBindingScope, ...]:
    scopes: dict[str, _DeletionBindingScope] = {}
    for binding in bindings:
        binding_id = str(getattr(binding, "binding_id", "") or "").strip()
        if not _BINDING_ID_RE.fullmatch(binding_id):
            raise MetaDeletionStateError("Meta deletion binding scope is invalid")
        generation = _safe_int(getattr(binding, "generation", 0), field="binding generation", minimum=1)
        scopes[binding_id] = _DeletionBindingScope(binding_id, generation)
    return tuple(sorted(scopes.values(), key=lambda item: item.binding_id))


def _new_request(
    *,
    confirmation_code: str,
    app_key: str,
    app_id: str,
    auth_flow: AuthFlow,
    bindings: tuple[_DeletionBindingScope, ...],
    required_nodes: tuple[str, ...],
    now: int,
) -> _SharedDeletionRequest:
    return _SharedDeletionRequest(
        confirmation_code=confirmation_code,
        app_key=app_key,
        app_id=app_id,
        auth_flow=auth_flow,
        bindings=bindings,
        current_bindings=bindings,
        generation=1,
        required_nodes=required_nodes,
        state="pending",
        coordinator_state="pending",
        requested_at=now,
        updated_at=now,
        completed_at=None,
        revoked_bindings=0,
        shared_redacted_documents=0,
        redacted_ledger_documents=0,
        safe_error="none",
    )


def _merge_request_scope(
    request: _SharedDeletionRequest,
    current: tuple[_DeletionBindingScope, ...],
    *,
    required_nodes: tuple[str, ...],
    now: int,
) -> _SharedDeletionRequest:
    if request.required_nodes != required_nodes:
        raise MetaDeletionStateError("Meta deletion required-node configuration changed")
    existing = {item.binding_id: item for item in request.bindings}
    additions = [item for item in current if item.binding_id not in existing]
    merged = tuple(sorted((*request.bindings, *additions), key=lambda item: item.binding_id))
    if current != request.current_bindings:
        return _SharedDeletionRequest(
            **{
                **request.__dict__,
                "bindings": merged,
                "current_bindings": current,
                "generation": request.generation + 1,
                "state": "pending",
                "coordinator_state": "pending",
                "updated_at": now,
                "completed_at": None,
                "revoked_bindings": 0,
                "shared_redacted_documents": 0,
                "redacted_ledger_documents": 0,
                "safe_error": "none",
            }
        )
    if request.state == "failed":
        return _SharedDeletionRequest(
            **{
                **request.__dict__,
                "state": "pending",
                "updated_at": now,
                "completed_at": None,
                "safe_error": "none",
            }
        )
    return request


def _get_or_create_shared_request(
    *,
    db: Any,
    subject_key: str,
    app_key: str,
    app_id: str,
    auth_flow: AuthFlow,
    bindings: tuple[_DeletionBindingScope, ...],
    required_nodes: tuple[str, ...],
) -> _SharedDeletionRequest:
    index_ref = _subject_index_ref(db, subject_key)
    last_error: Exception | None = None
    for _attempt in range(5):
        try:
            now = int(time.time())

            def _get_or_create(transaction: Any, now: int = now) -> _SharedDeletionRequest:
                index_snapshot = index_ref.get(transaction=transaction)
                if index_snapshot.exists:
                    index_data = _snapshot_payload(index_snapshot, label="subject index")
                    if not set(index_data).issubset(_INDEX_SAFE_FIELDS):
                        raise MetaDeletionStateError("Meta deletion subject index contains unsafe fields")
                    code = str(index_data.get("confirmation_code") or "").strip().lower()
                    if _safe_int(
                        index_data.get("schema_version"), field="index schema", minimum=1
                    ) != _SCHEMA_VERSION or not _CONFIRMATION_CODE_RE.fullmatch(code):
                        raise MetaDeletionStateError("Meta deletion subject index is invalid")
                    request_ref = _request_ref(db, code)
                    request = _parse_shared_request(
                        _snapshot_payload(request_ref.get(transaction=transaction), label="request"),
                        code,
                    )
                    if request.app_key != app_key or request.app_id != app_id or request.auth_flow != auth_flow:
                        raise MetaDeletionStateError("Meta deletion signing domain does not match")
                    merged = _merge_request_scope(request, bindings, required_nodes=required_nodes, now=now)
                    if merged != request:
                        transaction.set(request_ref, _request_payload(merged))
                    return merged

                code = generate_opaque_confirmation_code()
                request_ref = _request_ref(db, code)
                if request_ref.get(transaction=transaction).exists:
                    raise MetaDeletionStateError("Meta deletion confirmation collision")
                request = _new_request(
                    confirmation_code=code,
                    app_key=app_key,
                    app_id=app_id,
                    auth_flow=auth_flow,
                    bindings=bindings,
                    required_nodes=required_nodes,
                    now=now,
                )
                transaction.set(
                    index_ref,
                    {
                        "schema_version": _SCHEMA_VERSION,
                        "confirmation_code": code,
                        "created_at": now,
                    },
                )
                transaction.set(request_ref, _request_payload(request))
                return request

            return run_firestore_transaction(db, _get_or_create)
        except MetaDeletionStateError:
            raise
        except Exception as exc:
            last_error = exc
            continue
    raise MetaDeletionStoreUnavailableError("Meta deletion transaction failed") from last_error


def _read_shared_request(db: Any, confirmation_code: str) -> _SharedDeletionRequest | None:
    try:
        snapshot = _request_ref(db, confirmation_code).get()
    except Exception as exc:
        raise MetaDeletionStoreUnavailableError("Meta deletion request read failed") from exc
    if not snapshot.exists:
        return None
    return _parse_shared_request(_snapshot_payload(snapshot, label="request"), confirmation_code)


def _replace_request_if_generation(
    db: Any,
    request: _SharedDeletionRequest,
    updated: _SharedDeletionRequest,
) -> _SharedDeletionRequest:
    reference = _request_ref(db, request.confirmation_code)
    last_error: Exception | None = None
    for _attempt in range(5):
        try:

            def _replace(transaction: Any) -> _SharedDeletionRequest:
                current = _parse_shared_request(
                    _snapshot_payload(reference.get(transaction=transaction), label="request"),
                    request.confirmation_code,
                )
                if current.generation != request.generation or current != request:
                    # A generation/same-generation winner owns the newer state. Never
                    # regress coordinator completion or a reopened request.
                    return current
                transaction.set(reference, _request_payload(updated))
                return updated

            return run_firestore_transaction(db, _replace)
        except MetaDeletionStateError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaDeletionStoreUnavailableError("Meta deletion request update failed") from last_error


def _mark_coordinator_failed(
    db: Any,
    request: _SharedDeletionRequest,
    *,
    safe_error: Literal["shared_preflight", "registry_conflict", "shared_redaction", "internal"],
) -> None:
    now = int(time.time())
    failed = _SharedDeletionRequest(
        **{
            **request.__dict__,
            "state": "failed",
            "updated_at": now,
            "completed_at": now,
            "safe_error": safe_error,
        }
    )
    try:
        _replace_request_if_generation(db, request, failed)
    except Exception:
        pass


def _mark_coordinator_completed(
    db: Any,
    request: _SharedDeletionRequest,
    *,
    revoked_bindings: int,
    shared_redacted_documents: int,
    current_bindings: tuple[_DeletionBindingScope, ...],
) -> _SharedDeletionRequest:
    if request.coordinator_state == "completed":
        return request
    updated = _SharedDeletionRequest(
        **{
            **request.__dict__,
            "state": "pending",
            "coordinator_state": "completed",
            "current_bindings": current_bindings,
            "updated_at": int(time.time()),
            "completed_at": None,
            "revoked_bindings": max(0, int(revoked_bindings)),
            "shared_redacted_documents": max(0, int(shared_redacted_documents)),
            "redacted_ledger_documents": max(0, int(shared_redacted_documents)),
            "safe_error": "none",
        }
    )
    return _replace_request_if_generation(db, request, updated)


def _redaction_has_remaining(stats: dict[str, int | bool], *, shared: bool) -> bool:
    key = "firestore_changed" if shared else "local_changed"
    return int(stats.get(key) or 0) > 0


def _parse_ack(value: object, *, node_id: str, request_generation: int) -> int | None:
    if not isinstance(value, dict):
        return None
    if not set(value).issubset(_ACK_SAFE_FIELDS):
        return None
    if (
        value.get("schema_version") != _SCHEMA_VERSION
        or str(value.get("node_id") or "") != node_id
        or str(value.get("status") or "") != "completed"
        or value.get("request_generation") != request_generation
        or value.get("local_blockers") != 0
        or value.get("local_remaining_changes") != 0
    ):
        return None
    try:
        return _safe_int(value.get("local_redacted_documents") or 0, field="node redaction count")
    except MetaDeletionStateError:
        return None


def _finalize_shared_request(db: Any, confirmation_code: str) -> _SharedDeletionRequest:
    request_ref = _request_ref(db, confirmation_code)
    last_error: Exception | None = None
    for _attempt in range(5):
        try:

            def _finalize(transaction: Any) -> _SharedDeletionRequest:
                request = _parse_shared_request(
                    _snapshot_payload(request_ref.get(transaction=transaction), label="request"),
                    confirmation_code,
                )
                if request.state in {"completed", "no_data"}:
                    return request
                if request.state != "pending" or request.coordinator_state != "completed":
                    return request
                local_redacted = 0
                for required_node in request.required_nodes:
                    ack_ref = request_ref.collection("node_acks").document(required_node)
                    ack_snapshot = ack_ref.get(transaction=transaction)
                    if not ack_snapshot.exists:
                        return request
                    count = _parse_ack(
                        _snapshot_payload(ack_snapshot, label="node acknowledgement"),
                        node_id=required_node,
                        request_generation=request.generation,
                    )
                    if count is None:
                        return request
                    local_redacted += count
                now = int(time.time())
                final_state: Literal["completed", "no_data"] = "completed" if request.bindings else "no_data"
                completed = _SharedDeletionRequest(
                    **{
                        **request.__dict__,
                        "state": final_state,
                        "updated_at": now,
                        "completed_at": now,
                        "redacted_ledger_documents": request.shared_redacted_documents + local_redacted,
                        "safe_error": "none",
                    }
                )
                transaction.set(request_ref, _request_payload(completed))
                return completed

            return run_firestore_transaction(db, _finalize)
        except MetaDeletionStateError:
            raise
        except Exception as exc:
            last_error = exc
    raise MetaDeletionStoreUnavailableError("Meta deletion finalization failed") from last_error


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
