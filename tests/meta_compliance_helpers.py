"""Signed-request helpers and fake Firestore for Meta compliance tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

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


class _FakeQuery:
    def __init__(self, documents: list[_FakeDocument]) -> None:
        self.documents = documents

    def stream(self) -> list[_FakeSnapshot]:
        return [_FakeSnapshot(document) for document in self.documents if document.exists]


class _FakeCollection:
    def __init__(self, path: str) -> None:
        self.path = path
        self.documents: dict[str, _FakeDocument] = {}

    def document(self, document_id: str) -> _FakeDocument:
        if document_id not in self.documents:
            self.documents[document_id] = _FakeDocument(f"{self.path}/{document_id}", exists=False)
        return self.documents[document_id]

    def stream(self) -> list[_FakeSnapshot]:
        return [_FakeSnapshot(document) for document in self.documents.values() if document.exists]

    def where(self, field: str, operator: str, value: str) -> _FakeQuery:
        assert operator == "=="
        return _FakeQuery(
            [document for document in self.documents.values() if document.exists and document.data.get(field) == value]
        )


class _FakeDocument:
    def __init__(self, path: str, *, exists: bool = True, data: dict[str, str] | None = None) -> None:
        self.path = path
        self.exists = exists
        self.data = data or {}
        self._collections: dict[str, _FakeCollection] = {}

    @property
    def reference(self) -> _FakeDocument:
        return self

    def get(self) -> _FakeSnapshot:
        return _FakeSnapshot(self)

    def collection(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection(f"{self.path}/{name}")
        return self._collections[name]

    def collections(self) -> list[_FakeCollection]:
        return list(self._collections.values())

    def delete(self) -> None:
        self.exists = False


class _FakeFirestore:
    def __init__(self) -> None:
        self._collections: dict[str, _FakeCollection] = {}

    def collection(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection(name)
        return self._collections[name]
