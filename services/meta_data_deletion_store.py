"""Shared Firestore request store, merge, and coordinator updates."""

from __future__ import annotations

import time
from typing import Any, Literal

from services.firestore_transaction_compat import run_firestore_transaction
from services.meta_app_registry_common import AuthFlow
from services.meta_data_deletion_types import (
    _ACK_SAFE_FIELDS,
    _BINDING_ID_RE,
    _CONFIRMATION_CODE_RE,
    _INDEX_SAFE_FIELDS,
    _NODE_ID_RE,
    _REQUEST_SAFE_FIELDS,
    _SCHEMA_VERSION,
    MetaDeletionStateError,
    MetaDeletionStoreUnavailableError,
    _DeletionBindingScope,
    _request_ref,
    _safe_int,
    _SharedDeletionRequest,
    _subject_index_ref,
    generate_opaque_confirmation_code,
)


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
