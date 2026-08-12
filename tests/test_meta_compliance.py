"""Public Meta compliance pages and authenticated deletion callback tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from services.meta_app_registry import APP_A_KEY
from services.meta_data_deletion import (
    MetaDeletionResult,
    MetaSignedRequestError,
    deletion_confirmation_code,
    generate_opaque_confirmation_code,
    verify_meta_deletion_signed_request,
)
from tests.meta_compliance_helpers import APP_A_ENV, APP_SECRET, _signed_request


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
        ("/privacy-policy", "Roles and relationships"),
        ("/terms", "does not create, edit, reschedule"),
        ("/data-deletion", "Invalid signatures are rejected"),
    ):
        response = compliance_client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert response.headers["x-frame-options"] == "DENY"
        assert marker in response.text
        assert "Linas AI" in response.text
        assert "support@linasai.com" in response.text

    privacy = compliance_client.get("/privacy-policy")
    assert "WhatsApp" in privacy.text
    assert "TikTok" in privacy.text
    assert "AI Setup" in privacy.text
    assert "Owner chat" in privacy.text
    assert "Facebook" in privacy.text
    assert "Instagram" in privacy.text
    assert "Children’s privacy" in privacy.text or "Children's privacy" in privacy.text
    assert "International transfers" in privacy.text
    assert "OpenAI" in privacy.text
    assert "In-App Purchase" in privacy.text or "Apple" in privacy.text
    assert "mobile app" in privacy.text

    terms = compliance_client.get("/terms")
    assert "WhatsApp" in terms.text
    assert "TikTok" in terms.text
    assert "Limitation of liability" in terms.text
    assert "AI Setup" in terms.text
    assert "business customer-support" in terms.text

    deletion = compliance_client.get("/data-deletion")
    assert "WhatsApp" in deletion.text
    assert "TikTok" in deletion.text
    assert "Linas AI account deletion" in deletion.text
    assert "30 days" in deletion.text
    assert "Social message data deletion" in deletion.text


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
