"""Signed-request helpers and fake Firestore for Meta compliance tests."""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import threading
import time
from typing import Any

APP_SECRET = "new-app-unit-secret"
APP_A_ENV = {
    "META_APP_A_ID": "2963733803971681",
    "META_APP_A_SECRET": APP_SECRET,
    "META_APP_A_WEBHOOK_VERIFY_TOKEN": "verify-a-tests",
}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _signed_request(
    *,
    secret: str = APP_SECRET,
    user_id: str = "123456789",
    issued_at: int | None = None,
    algorithm: str = "HMAC-SHA256",
) -> str:
    payload = {
        "algorithm": algorithm,
        "issued_at": int(time.time()) if issued_at is None else issued_at,
        "user_id": user_id,
    }
    encoded_payload = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256).digest()
    return f"{_b64url(signature)}.{encoded_payload}"


class _FakeSnapshot:
    def __init__(self, reference: _FakeDocument) -> None:
        self.reference = reference
        self.exists = reference.exists
        self.version = reference.version
        self._data = copy.deepcopy(reference.data)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)


class _FakeQuery:
    def __init__(self, documents: list[_FakeDocument]) -> None:
        self.documents = documents

    def stream(self) -> list[_FakeSnapshot]:
        return [_FakeSnapshot(document) for document in self.documents if document.exists]


class _FakeCollection:
    def __init__(self, path: str, *, lock: threading.RLock | None = None) -> None:
        self.path = path
        self._lock = lock or threading.RLock()
        self.documents: dict[str, _FakeDocument] = {}

    def document(self, document_id: str) -> _FakeDocument:
        if document_id not in self.documents:
            self.documents[document_id] = _FakeDocument(
                f"{self.path}/{document_id}",
                exists=False,
                lock=self._lock,
            )
        return self.documents[document_id]

    def stream(self) -> list[_FakeSnapshot]:
        return [_FakeSnapshot(document) for document in self.documents.values() if document.exists]

    def where(self, field: str, operator: str, value: str) -> _FakeQuery:
        assert operator == "=="
        return _FakeQuery(
            [document for document in self.documents.values() if document.exists and document.data.get(field) == value]
        )


class _FakeDocument:
    def __init__(
        self,
        path: str,
        *,
        exists: bool = True,
        data: dict[str, Any] | None = None,
        lock: threading.RLock | None = None,
    ) -> None:
        self.path = path
        self.exists = exists
        self.data = data or {}
        self.version = 0
        self._lock = lock or threading.RLock()
        self._collections: dict[str, _FakeCollection] = {}

    @property
    def reference(self) -> _FakeDocument:
        return self

    def get(self, *, transaction: _FakeTransaction | None = None) -> _FakeSnapshot:
        with self._lock:
            snapshot = _FakeSnapshot(self)
            if transaction is not None:
                transaction.record_read(self, snapshot.version)
            return snapshot

    def collection(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection(f"{self.path}/{name}", lock=self._lock)
        return self._collections[name]

    def collections(self) -> list[_FakeCollection]:
        return list(self._collections.values())

    def delete(self) -> None:
        with self._lock:
            self.exists = False
            self.version += 1

    def update(self, updates: dict[str, Any]) -> None:
        with self._lock:
            self.data.update(copy.deepcopy(updates))
            self.exists = True
            self.version += 1

    def set(self, data: dict[str, Any]) -> None:
        with self._lock:
            self.data = copy.deepcopy(data)
            self.exists = True
            self.version += 1


class _FakeTransaction:
    def __init__(self, lock: threading.RLock) -> None:
        self._lock = lock
        self._reads: dict[_FakeDocument, int] = {}
        self._writes: list[tuple[_FakeDocument, dict[str, Any]]] = []

    def record_read(self, document: _FakeDocument, version: int) -> None:
        self._reads.setdefault(document, version)

    def set(self, document: _FakeDocument, data: dict[str, Any]) -> None:
        self._writes.append((document, copy.deepcopy(data)))

    def commit(self) -> None:
        with self._lock:
            if any(document.version != version for document, version in self._reads.items()):
                raise RuntimeError("ABORTED: fake Firestore transaction conflict")
            for document, data in self._writes:
                document.set(data)


class _FakeFirestore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._collections: dict[str, _FakeCollection] = {}

    def collection(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection(name, lock=self._lock)
        return self._collections[name]

    def transaction(self) -> _FakeTransaction:
        return _FakeTransaction(self._lock)


def _set_fake_meta_deletion_request(
    db: _FakeFirestore,
    *,
    subject_key: str,
    app_key: str,
    app_id: str,
    auth_flow: str,
    state: str,
    generation: int = 1,
    code: str = "a" * 32,
) -> None:
    """Populate the strict shared request shape used by OAuth guard tests."""

    app = db.collection("artifacts").document("linas-ai-bot-backend")
    app.collection("meta_deletion_subject_index").document(subject_key).set(
        {"schema_version": 1, "confirmation_code": code, "created_at": 100}
    )
    app.collection("meta_deletion_requests").document(code).set(
        {
            "schema_version": 1,
            "confirmation_code": code,
            "app_key": app_key,
            "app_id": app_id,
            "auth_flow": auth_flow,
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
