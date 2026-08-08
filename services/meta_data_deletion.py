"""Verification and deletion helpers for Meta's user-data deletion callback."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import config
from storage.persistent_storage import _DATA_ROOT

_META_USER_ID_RE = re.compile(r"^[0-9]{3,64}$")
_CONFIRMATION_CODE_RE = re.compile(r"^[0-9a-f]{32}$")
_MAX_SIGNED_REQUEST_AGE_SECONDS = 7 * 24 * 60 * 60
_MAX_FUTURE_SKEW_SECONDS = 5 * 60
_STATUS_DIR = Path(_DATA_ROOT) / "meta_deletion_status"
_INDEX_DIR = Path(_DATA_ROOT) / "meta_deletion_index"
_FIRESTORE_APP_ID = "linas-ai-bot-backend"
DeletionStatus = Literal["received", "pending", "completed", "no_data", "failed"]


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


class MetaSignedRequestError(ValueError):
    """Raised when Meta's signed_request is malformed, stale, or unauthentic."""


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


def _index_path(app_key: str, meta_user_id: str) -> Path:
    digest = hashlib.sha256(f"{app_key}:{meta_user_id}".encode()).hexdigest()
    return _INDEX_DIR / f"{digest}.json"


def _lookup_existing_confirmation_code(app_key: str, meta_user_id: str) -> str | None:
    path = _index_path(app_key, meta_user_id)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    code = str(payload.get("confirmation_code") or "").strip().lower()
    if not _CONFIRMATION_CODE_RE.fullmatch(code):
        return None
    return code


def _remember_confirmation_code(app_key: str, meta_user_id: str, confirmation_code: str) -> None:
    _INDEX_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(_INDEX_DIR, 0o700)
    path = _index_path(app_key, meta_user_id)
    payload = {
        "confirmation_code": confirmation_code,
        "app_key": app_key,
        "created_at": int(time.time()),
    }
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)
    os.chmod(path, 0o600)


def _delete_document_tree(document_ref: Any) -> int:
    """Recursively delete one Firestore document and all nested documents."""
    deleted = 0
    for collection_ref in document_ref.collections():
        for snapshot in collection_ref.stream():
            deleted += _delete_document_tree(snapshot.reference)
    document_ref.delete()
    return deleted + 1


def _delete_live_chat_index_rows(db: Any, candidate_user_ids: tuple[str, ...]) -> int:
    index = db.collection("artifacts").document(_FIRESTORE_APP_ID).collection("live_chat_index")
    deleted_paths: set[str] = set()
    for candidate in candidate_user_ids:
        for snapshot in index.where("user_id", "==", candidate).stream():
            path = str(snapshot.reference.path)
            if path in deleted_paths:
                continue
            snapshot.reference.delete()
            deleted_paths.add(path)
    return len(deleted_paths)


def _clear_in_memory_social_state(candidate_user_ids: tuple[str, ...]) -> None:
    mapping_names = (
        "user_context",
        "user_gender",
        "gender_attempts",
        "user_names",
        "user_greeting_stage",
        "user_in_training_mode",
        "user_photo_analysis_count",
        "user_last_bot_response_time",
        "user_pending_messages",
        "user_data_whatsapp",
        "user_in_human_takeover_mode",
        "user_last_waiting_reply_sent",
        "user_booking_state",
        "training_stage",
        "last_generated_qa_for_save",
    )
    for mapping_name in mapping_names:
        mapping = getattr(config, mapping_name, None)
        if not isinstance(mapping, MutableMapping):
            continue
        for candidate in candidate_user_ids:
            mapping.pop(candidate, None)
    from services.user_persistence_service import user_persistence

    for candidate in candidate_user_ids:
        user_persistence.clear_cache(candidate)


def _write_deletion_status(
    confirmation_code: str,
    *,
    status: DeletionStatus,
    requested_at: int,
    completed_at: int | None = None,
    deleted_user_documents: int = 0,
    deleted_nested_documents: int = 0,
    deleted_index_documents: int = 0,
) -> None:
    _STATUS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(_STATUS_DIR, 0o700)
    status_path = _STATUS_DIR / f"{confirmation_code}.json"
    payload: dict[str, Any] = {
        "confirmation_code": confirmation_code,
        "status": status,
        "requested_at": requested_at,
        "deleted_user_documents": deleted_user_documents,
        "deleted_nested_documents": deleted_nested_documents,
        "deleted_index_documents": deleted_index_documents,
    }
    if completed_at is not None:
        payload["completed_at"] = completed_at
    temporary = status_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(status_path)
    os.chmod(status_path, 0o600)


def read_deletion_status(confirmation_code: str) -> dict[str, Any] | None:
    code = str(confirmation_code or "").strip().lower()
    if not _CONFIRMATION_CODE_RE.fullmatch(code):
        return None
    status_path = _STATUS_DIR / f"{code}.json"
    if not status_path.is_file():
        return None
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("confirmation_code") != code:
        return None
    return cast(dict[str, Any], data)


def _candidate_social_user_ids(meta_user_id: str, app_key: str) -> tuple[str, ...]:
    from services.meta_app_registry import APP_A_KEY, get_meta_app_registry
    from services.social_user_id import compose_social_user_id

    candidates: set[str] = set()
    if app_key == APP_A_KEY:
        candidates.update({f"facebook:{meta_user_id}", f"instagram:{meta_user_id}"})
    try:
        bindings = get_meta_app_registry().list_bindings(include_superseded=False)
    except Exception:
        bindings = []
    for binding in bindings:
        if binding.app_key != app_key:
            continue
        candidates.add(f"{binding.tenant_id}:{binding.channel}:{meta_user_id}")
        candidates.add(
            compose_social_user_id(
                tenant_id=binding.tenant_id,
                channel=binding.channel,
                asset_id=binding.asset_id,
                sender_id=meta_user_id,
                multi_asset_channel=True,
            )
        )
        if binding.tenant_id == "linas":
            candidates.add(f"{binding.channel}:{meta_user_id}")
            candidates.add(f"{binding.channel}:{binding.asset_id}:{meta_user_id}")
    return tuple(sorted(candidates))


def delete_meta_social_user_data(
    meta_user_id: str,
    app_secret: str,
    *,
    app_key: str = "linas_first_party",
) -> MetaDeletionResult:
    """Delete only the namespaced Facebook/Instagram user associated with Meta's ID."""
    raw_user_id = str(meta_user_id or "").strip()
    if not _META_USER_ID_RE.fullmatch(raw_user_id):
        raise ValueError("Invalid Meta user identifier")
    if not str(app_secret or "").strip():
        raise ValueError("App secret is required")

    existing_code = _lookup_existing_confirmation_code(app_key, raw_user_id)
    confirmation_code = existing_code or generate_opaque_confirmation_code()
    requested_at = int(time.time())
    if existing_code is None:
        _remember_confirmation_code(app_key, raw_user_id, confirmation_code)
    _write_deletion_status(confirmation_code, status="received", requested_at=requested_at)
    _write_deletion_status(confirmation_code, status="pending", requested_at=requested_at)

    from utils.utils import get_firestore_db

    db = get_firestore_db()
    if db is None:
        _write_deletion_status(confirmation_code, status="failed", requested_at=requested_at)
        raise RuntimeError("Firestore is unavailable")

    candidates = _candidate_social_user_ids(raw_user_id, app_key)
    users = db.collection("artifacts").document(_FIRESTORE_APP_ID).collection("users")
    deleted_users = 0
    deleted_nested = 0
    for candidate in candidates:
        user_ref = users.document(candidate)
        snapshot = user_ref.get()
        if not snapshot.exists:
            continue
        deleted_total = _delete_document_tree(user_ref)
        deleted_users += 1
        deleted_nested += max(0, deleted_total - 1)

    deleted_indexes = _delete_live_chat_index_rows(db, candidates)
    _clear_in_memory_social_state(candidates)
    completed_at = int(time.time())
    final_status: DeletionStatus = "completed" if (deleted_users or deleted_indexes) else "no_data"
    _write_deletion_status(
        confirmation_code,
        status=final_status,
        requested_at=requested_at,
        completed_at=completed_at,
        deleted_user_documents=deleted_users,
        deleted_nested_documents=deleted_nested,
        deleted_index_documents=deleted_indexes,
    )
    return MetaDeletionResult(
        confirmation_code=confirmation_code,
        deleted_user_documents=deleted_users,
        deleted_nested_documents=deleted_nested,
        deleted_index_documents=deleted_indexes,
    )
