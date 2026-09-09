"""Types, errors, and signed-request verification for Meta data deletion."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Literal, cast

from services.meta_app_registry_common import AuthFlow

_META_USER_ID_RE = re.compile(r"^[0-9]{3,64}$")
_CONFIRMATION_CODE_RE = re.compile(r"^[0-9a-f]{32}$")
_NODE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_BINDING_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
_MAX_SIGNED_REQUEST_AGE_SECONDS = 7 * 24 * 60 * 60
_MAX_FUTURE_SKEW_SECONDS = 5 * 60
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
