"""Public Meta compliance pages and authenticated deletion callback tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from services.meta_app_registry import APP_A_KEY
from services.meta_data_deletion import (
    MetaDeletionResult,
    MetaSignedRequestError,
    delete_meta_social_user_data,
    deletion_confirmation_code,
    generate_opaque_confirmation_code,
    read_deletion_status,
    verify_meta_deletion_signed_request,
)

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


@pytest.fixture(scope="module")
def compliance_client() -> TestClient:
    import modules.meta_compliance  # noqa: F401
    from modules.core import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _configure_app_a(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in APP_A_ENV.items():
        monkeypatch.setenv(key, value)


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


def test_opaque_confirmation_code_is_random_and_not_pii() -> None:
    first = generate_opaque_confirmation_code()
    second = generate_opaque_confirmation_code()
    assert first != second
    assert re.fullmatch(r"[0-9a-f]{32}", first)
    assert "123456789" not in first


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


@pytest.mark.parametrize(
    "path",
    [
        "/oauth/meta/data-deletion",
        "/oauth/meta/deauthorize",
    ],
)
def test_meta_callback_health_is_reachable(compliance_client: TestClient, path: str) -> None:
    for method in ("get", "head"):
        response = getattr(compliance_client, method)(path)
        assert response.status_code == 200
        if method == "get":
            assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    [
        "/oauth/meta/data-deletion",
        "/data-deletion",
    ],
)
def test_invalid_deletion_signed_request_returns_400(
    compliance_client: TestClient,
    path: str,
) -> None:
    response = compliance_client.post(path, data={"signed_request": _signed_request(secret="wrong")})
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid signed deletion request"}


def test_missing_deletion_signed_request_returns_400(compliance_client: TestClient) -> None:
    response = compliance_client.post("/oauth/meta/data-deletion", data={})
    assert response.status_code == 400


def test_valid_deletion_callback_returns_meta_contract(compliance_client: TestClient) -> None:
    result = MetaDeletionResult(
        confirmation_code="a" * 32,
        deleted_user_documents=1,
        deleted_nested_documents=2,
        deleted_index_documents=1,
    )
    with mock.patch("modules.meta_compliance.delete_meta_social_user_data", return_value=result) as delete_mock:
        response = compliance_client.post(
            "/oauth/meta/data-deletion",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 200
    assert response.json() == {
        "url": f"https://www.linasaibot.com/data-deletion/status/{'a' * 32}",
        "confirmation_code": "a" * 32,
    }
    delete_mock.assert_called_once_with(
        "123456789",
        APP_SECRET,
        app_key=APP_A_KEY,
    )


def test_legacy_data_deletion_route_still_works(compliance_client: TestClient) -> None:
    result = MetaDeletionResult(
        confirmation_code="c" * 32,
        deleted_user_documents=0,
        deleted_nested_documents=0,
        deleted_index_documents=0,
    )
    with mock.patch("modules.meta_compliance.delete_meta_social_user_data", return_value=result):
        response = compliance_client.post("/data-deletion", data={"signed_request": _signed_request()})
    assert response.status_code == 200
    assert response.json()["confirmation_code"] == "c" * 32


def test_app_a_deauthorization_revokes_only_authenticated_owner_connections(
    compliance_client: TestClient,
) -> None:
    registry = mock.Mock()
    with mock.patch("modules.meta_compliance.get_meta_app_registry", return_value=registry):
        response = compliance_client.post(
            "/oauth/meta/deauthorize",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 200
    assert response.json() == {"success": True}
    registry.revoke_authorization.assert_called_once_with(
        app_key=APP_A_KEY,
        authorized_meta_user_id="123456789",
    )


def test_legacy_deauthorize_route_still_works(compliance_client: TestClient) -> None:
    registry = mock.Mock()
    with mock.patch("modules.meta_compliance.get_meta_app_registry", return_value=registry):
        response = compliance_client.post(
            "/meta/deauthorize",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 200
    registry.revoke_authorization.assert_called_once_with(
        app_key=APP_A_KEY,
        authorized_meta_user_id="123456789",
    )


def test_invalid_deauthorization_signature_is_rejected_without_registry_access(
    compliance_client: TestClient,
) -> None:
    with mock.patch("modules.meta_compliance.get_meta_app_registry") as registry:
        response = compliance_client.post(
            "/oauth/meta/deauthorize",
            data={"signed_request": _signed_request(secret="wrong-secret")},
        )
    assert response.status_code == 400
    registry.assert_not_called()


def test_callback_never_reports_success_when_deletion_fails(compliance_client: TestClient) -> None:
    with mock.patch(
        "modules.meta_compliance.delete_meta_social_user_data",
        side_effect=RuntimeError("simulated storage failure"),
    ):
        response = compliance_client.post(
            "/oauth/meta/data-deletion",
            data={"signed_request": _signed_request()},
        )
    assert response.status_code == 503
    assert response.json() == {"detail": "Data deletion could not be completed"}


def test_public_status_page_does_not_expose_pii(compliance_client: TestClient, tmp_path: Path) -> None:
    import services.meta_data_deletion as deletion_service

    code = "d" * 32
    monkeypatch_dir = tmp_path / "status"
    monkeypatch_dir.mkdir()
    status_path = monkeypatch_dir / f"{code}.json"
    status_path.write_text(
        json.dumps(
            {
                "confirmation_code": code,
                "status": "completed",
                "requested_at": 1_800_000_000,
                "completed_at": 1_800_000_100,
            }
        ),
        encoding="utf-8",
    )
    with mock.patch.object(deletion_service, "_STATUS_DIR", monkeypatch_dir):
        response = compliance_client.get(f"/data-deletion/status/{code}")
    assert response.status_code == 200
    assert "noindex" in response.text
    assert code in response.text
    assert "123456789" not in response.text
    assert "completed" in response.text


def test_unknown_status_code_returns_safe_message(compliance_client: TestClient) -> None:
    response = compliance_client.get("/data-deletion/status/" + ("e" * 32))
    assert response.status_code == 200
    assert "could not find" in response.text.lower()
    assert "123456789" not in response.text


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
    monkeypatch.setattr(deletion_service, "_INDEX_DIR", tmp_path / "index")

    result = delete_meta_social_user_data("123456789", APP_SECRET)

    assert result.deleted_user_documents == 1
    assert result.deleted_nested_documents == 1
    assert result.deleted_index_documents == 1
    assert facebook_user.exists is False
    assert nested.exists is False
    assert index.documents["index-1"].exists is False
    assert "facebook:123456789" not in config.user_data_whatsapp
    assert "123456789" not in result.confirmation_code
    status = read_deletion_status(result.confirmation_code)
    assert status is not None
    assert status["status"] == "completed"
    assert (tmp_path / "status" / f"{result.confirmation_code}.json").stat().st_mode & 0o777 == 0o600


def test_repeated_deletion_request_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import services.meta_data_deletion as deletion_service
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(deletion_service, "_INDEX_DIR", tmp_path / "index")

    first = delete_meta_social_user_data("123456789", APP_SECRET)
    second = delete_meta_social_user_data("123456789", APP_SECRET)
    assert first.confirmation_code == second.confirmation_code
    assert read_deletion_status(second.confirmation_code)["status"] == "no_data"


def test_tenant_namespaced_deletion_does_not_touch_unrelated_user(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import config
    import services.meta_app_registry as registry_service
    import services.meta_data_deletion as deletion_service
    import utils.utils

    db = _FakeFirestore()
    app = db.collection("artifacts").document("linas-ai-bot-backend")
    users = app.collection("users")
    tenant_user = users.document("tenant-a:facebook:123456789")
    tenant_user.exists = True
    unrelated_user = users.document("tenant-b:facebook:987654321")
    unrelated_user.exists = True
    index = app.collection("live_chat_index")
    index.documents["tenant-index"] = _FakeDocument(
        f"{index.path}/tenant-index",
        data={"user_id": "tenant-a:facebook:123456789"},
    )
    config.user_data_whatsapp["tenant-a:facebook:123456789"] = {"temporary": True}

    fake_registry = SimpleNamespace(
        list_bindings=lambda *args, **kwargs: [
            SimpleNamespace(
                app_key=APP_A_KEY,
                tenant_id="tenant-a",
                channel="facebook",
                asset_id="page-tenant-a",
            )
        ]
    )
    monkeypatch.setattr(registry_service, "get_meta_app_registry", lambda: fake_registry)
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    monkeypatch.setattr(deletion_service, "_STATUS_DIR", tmp_path / "status")
    monkeypatch.setattr(deletion_service, "_INDEX_DIR", tmp_path / "index")

    result = delete_meta_social_user_data("123456789", APP_SECRET, app_key=APP_A_KEY)
    assert result.deleted_user_documents == 1
    assert tenant_user.exists is False
    assert unrelated_user.exists is True
    assert index.documents["tenant-index"].exists is False


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
        "/oauth/meta/deauthorize",
        "/oauth/meta/data-deletion",
        "/data-deletion/status/{confirmation_code}",
        "/meta/deauthorize",
    } <= registered_paths
