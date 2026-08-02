"""Public Meta compliance pages and authenticated deletion callback tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from services.meta_data_deletion import (
    MetaDeletionResult,
    MetaSignedRequestError,
    delete_meta_social_user_data,
    deletion_confirmation_code,
    read_deletion_status,
    verify_meta_deletion_signed_request,
)

APP_SECRET = "new-app-unit-secret"


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


@pytest.fixture(scope="module")
def compliance_client() -> TestClient:
    import modules.meta_compliance  # noqa: F401
    from modules.core import app

    return TestClient(app)


def test_meta_signed_request_success() -> None:
    issued_at = 1_800_000_000
    verified = verify_meta_deletion_signed_request(
        _signed_request(issued_at=issued_at),
        APP_SECRET,
        now=issued_at + 10,
    )
    assert verified.meta_user_id == "123456789"
    assert verified.issued_at == issued_at


@pytest.mark.parametrize(
    "signed_request,secret,now",
    [
        (_signed_request(), "wrong-secret", None),
        (_signed_request(algorithm="none"), APP_SECRET, None),
        (_signed_request(user_id="facebook:123"), APP_SECRET, None),
        (_signed_request(issued_at=1_700_000_000), APP_SECRET, 1_800_000_000),
        ("malformed", APP_SECRET, None),
    ],
)
def test_meta_signed_request_rejects_invalid_input(signed_request: str, secret: str, now: int | None) -> None:
    with pytest.raises(MetaSignedRequestError):
        verify_meta_deletion_signed_request(signed_request, secret, now=now)


def test_confirmation_code_does_not_expose_meta_id() -> None:
    code = deletion_confirmation_code("123456789", APP_SECRET)
    assert len(code) == 32
    assert "123456789" not in code


def test_public_compliance_pages_are_real_html(compliance_client: TestClient) -> None:
    for path, marker in (
        ("/privacy-policy", "Facebook Messenger and Instagram direct"),
        ("/terms", "does not create, edit, reschedule"),
        ("/data-deletion", "Invalid signatures are rejected"),
    ):
        response = compliance_client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["x-frame-options"] == "DENY"
        assert marker in response.text
        assert "Lina's Laser Clinics" in response.text


def test_invalid_deletion_signed_request_returns_401(
    compliance_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    response = compliance_client.post("/data-deletion", data={"signed_request": _signed_request(secret="wrong")})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid signed deletion request"}


def test_missing_deletion_signed_request_returns_401(
    compliance_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    response = compliance_client.post("/data-deletion", data={})
    assert response.status_code == 401


def test_valid_deletion_callback_returns_meta_contract(
    compliance_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    result = MetaDeletionResult(
        confirmation_code="a" * 32,
        deleted_user_documents=1,
        deleted_nested_documents=2,
        deleted_index_documents=1,
    )
    with mock.patch("modules.meta_compliance.delete_meta_social_user_data", return_value=result) as delete_mock:
        response = compliance_client.post("/data-deletion", data={"signed_request": _signed_request()})
    assert response.status_code == 200
    assert response.json() == {
        "url": f"https://www.linasaibot.com/data-deletion?confirmation_code={'a' * 32}",
        "confirmation_code": "a" * 32,
    }
    delete_mock.assert_called_once_with("123456789", APP_SECRET)


def test_callback_never_reports_success_when_deletion_fails(
    compliance_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("META_APP_SECRET", APP_SECRET)
    with mock.patch(
        "modules.meta_compliance.delete_meta_social_user_data",
        side_effect=RuntimeError("simulated storage failure"),
    ):
        response = compliance_client.post("/data-deletion", data={"signed_request": _signed_request()})
    assert response.status_code == 503
    assert response.json() == {"detail": "Data deletion could not be completed"}


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


def test_real_deletion_removes_namespaced_user_tree_and_index(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import config
    import services.meta_data_deletion as deletion_service
    import utils.utils

    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    users = app.collection("users")
    facebook_user = users.document("facebook:123456789")
    facebook_user.exists = True
    nested = facebook_user.collection("conversations").document("conversation-1")
    nested.exists = True
    index = app.collection("live_chat_index")
    index.documents["index-1"] = _FakeDocument(
        f"{index.path}/index-1",
        data={"user_id": "facebook:123456789"},
    )
    config.user_data_whatsapp["facebook:123456789"] = {"temporary": True}

    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_STATUS_DIR", tmp_path / "status")

    result = delete_meta_social_user_data("123456789", APP_SECRET)

    assert result.deleted_user_documents == 1
    assert result.deleted_nested_documents == 1
    assert result.deleted_index_documents == 1
    assert facebook_user.exists is False
    assert nested.exists is False
    assert index.documents["index-1"].exists is False
    assert "facebook:123456789" not in config.user_data_whatsapp
    status = read_deletion_status(result.confirmation_code)
    assert status is not None
    assert status["status"] == "completed"
    assert (tmp_path / "status" / f"{result.confirmation_code}.json").stat().st_mode & 0o777 == 0o600


def test_production_main_route_inventory_is_explicit() -> None:
    import main

    main_source = Path("main.py").read_text(encoding="utf-8")
    for route_module in (
        "modules.webhook_handlers",
        "modules.meta_messaging_webhook",
        "modules.meta_compliance",
        "modules.dashboard_api",
        "modules.auth_api",
        "modules.live_chat_api",
    ):
        assert f"import {route_module}" in main_source
    registered_paths = {getattr(route, "path", "") for route in main.app.routes}
    assert {
        "/api/health",
        "/api/ready",
        "/api/auth/login",
        "/webhook",
        "/webhook/meta-messaging",
        "/privacy-policy",
        "/terms",
        "/data-deletion",
    } <= registered_paths
