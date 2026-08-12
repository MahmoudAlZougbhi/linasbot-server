"""SEC-041: FAQ save-all-languages write APIs require authz + tenant scope."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from services.dashboard_session_service import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, session_service

_ROUTE_MODULES = (
    "modules.cm_faq_api",
    "modules.local_qa_api_faq",
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
    os.environ.setdefault("LINASLASER_API_TOKEN", "test-token")
    os.environ.setdefault("DASHBOARD_AUTH_SECRET", "faq-authz-test-secret")
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("DISABLE_API_DOCS", "true")

    for mod in _ROUTE_MODULES:
        __import__(mod)

    from modules.core import app

    return TestClient(app)


def _clear_client_auth(client: TestClient) -> None:
    client.cookies.clear()
    client.headers.pop(CSRF_HEADER_NAME, None)


def _set_session(
    client: TestClient,
    *,
    role: str,
    user_id: str,
    tenant_id: str,
    permissions: dict[str, bool] | None = None,
) -> str:
    rec = session_service.create_session(
        user_id=user_id,
        email=f"{user_id}@example.com",
        role=role,
        permissions=permissions,
        tenant_id=tenant_id,
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
    client.headers[CSRF_HEADER_NAME] = rec.csrf_token
    return rec.csrf_token


@pytest.mark.usefixtures("enable_faq_plan")
class TestCmFaqWriteAuthz:
    def test_cm_faq_create_unauthenticated_401(self, client: TestClient) -> None:
        _clear_client_auth(client)
        response = client.post("/api/cm/faq", json={"question": "q", "answer": "a", "language": "en"})
        assert response.status_code == 401

    def test_cm_faq_create_forbidden_for_viewer(self, client: TestClient) -> None:
        _clear_client_auth(client)
        _set_session(client, role="viewer", user_id="faq-viewer", tenant_id="tenant_a")
        response = client.post("/api/cm/faq", json={"question": "q", "answer": "a", "language": "en"})
        assert response.status_code == 403

    def test_cm_faq_from_livechat_forbidden_without_live_chat(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_client_auth(client)
        # contentManagers without liveChat cannot use Live Chat FAQ save path
        _set_session(
            client,
            role="operator",
            user_id="faq-op-no-lc",
            tenant_id="tenant_a",
            permissions={
                "liveChat": False,
                "contentManagers": True,
                "dashboard": True,
            },
        )
        create = AsyncMock(return_value={"success": True, "qa_group_id": "qa_x", "count_created": 4})
        monkeypatch.setattr("services.cm.faq_integration.create_faq_pair_from_livechat", create)
        response = client.post(
            "/api/cm/faq/from-livechat",
            json={"question": "q", "answer": "a", "language": "en"},
        )
        assert response.status_code == 403
        create.assert_not_awaited()

    def test_cm_faq_variant_patch_wrong_tenant_cannot_save(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from services.cm.faq_integration import FaqIntegrationError

        _clear_client_auth(client)
        _set_session(client, role="admin", user_id="faq-admin-a", tenant_id="tenant_a")

        async def _update(**kwargs: Any) -> dict[str, Any]:
            # Simulate tenant-scoped miss: group owned by tenant_b
            if kwargs.get("tenant_id") == "tenant_a" and kwargs.get("qa_group_id") == "qa_other_tenant":
                raise FaqIntegrationError("FAQ group not found: qa_other_tenant")
            return {"success": True}

        monkeypatch.setattr("modules.cm_faq_api.update_cm_faq_variant", _update)
        response = client.patch(
            "/api/cm/faq/qa_other_tenant/variants/en",
            json={"answer": "hijacked answer across languages"},
        )
        assert response.status_code == 422
        assert "not found" in (response.json().get("detail") or "").lower()

    def test_cm_faq_create_uses_session_tenant_not_body_tenant(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_client_auth(client)
        _set_session(client, role="admin", user_id="faq-admin-b", tenant_id="tenant_b")

        seen: dict[str, Any] = {}

        async def _create(**kwargs: Any) -> dict[str, Any]:
            seen.update(kwargs)
            return {
                "success": True,
                "qa_group_id": "qa_tenant_b",
                "created_entries": [],
                "count_created": 4,
            }

        monkeypatch.setattr("modules.cm_faq_api.create_faq_pair", _create)
        monkeypatch.setattr("modules.cm_faq_api.find_duplicate_faq_groups", lambda **kwargs: [])
        monkeypatch.setattr(
            "services.faq_entitlements.assert_can_create_faq",
            lambda tenant_id: {"faq_enabled": True},
        )
        monkeypatch.setattr(
            "services.faq_entitlements.get_faq_entitlement",
            lambda tenant_id: {"faq_enabled": True, "quota_display": "ok"},
        )

        response = client.post(
            "/api/cm/faq",
            json={
                "question": "Price?",
                "answer": "Twenty",
                "language": "en",
                "tenant_id": "tenant_evil",  # must be ignored
            },
        )
        assert response.status_code == 200
        assert response.json().get("success") is True
        assert seen.get("tenant_id") == "tenant_b"


@pytest.mark.usefixtures("enable_faq_plan")
class TestLiveChatFaqWriteAuthz:
    def test_faq_update_answer_unauthenticated_401(self, client: TestClient) -> None:
        _clear_client_auth(client)
        response = client.post("/api/faq/update-answer", json={"faq_id": 1, "new_answer_text": "x"})
        assert response.status_code == 401

    def test_faq_create_forbidden_for_viewer(self, client: TestClient) -> None:
        _clear_client_auth(client)
        _set_session(client, role="viewer", user_id="lc-faq-viewer", tenant_id="linas")
        response = client.post(
            "/api/faq/create-from-livechat",
            json={"question_text": "q", "answer_text": "a", "question_language": "en"},
        )
        assert response.status_code == 403

    def test_faq_update_rejects_other_tenant_row(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        _clear_client_auth(client)
        _set_session(client, role="operator", user_id="lc-faq-op", tenant_id="tenant_a")

        foreign_row = {
            "question": "q",
            "answer": "a",
            "language": "en",
            "qa_group_id": "qa_foreign",
            "tenant_id": "tenant_b",
        }
        monkeypatch.setattr("modules.local_qa_api_faq.read_qa_pairs", lambda: [foreign_row])
        monkeypatch.setattr(
            "services.cm.faq_integration.get_cm_faq_group",
            lambda **kwargs: None,
        )
        writes: list[Any] = []
        monkeypatch.setattr(
            "modules.local_qa_api_faq.write_qa_pairs",
            lambda pairs: writes.append(pairs) or True,
        )

        response = client.post(
            "/api/faq/update-answer",
            json={"faq_id": 1, "new_answer_text": "stolen answer"},
        )
        assert response.status_code == 403
        assert "another tenant" in (response.json().get("detail") or "").lower()
        assert writes == []

    def test_faq_create_from_livechat_passes_session_tenant(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _clear_client_auth(client)
        _set_session(client, role="operator", user_id="lc-faq-create", tenant_id="tenant_a")

        seen: dict[str, Any] = {}

        async def _create(**kwargs: Any) -> dict[str, Any]:
            seen.update(kwargs)
            return {
                "success": True,
                "qa_group_id": "qa_a",
                "created_entries": [{"language": "en"}],
                "count_created": 4,
                "duplicates": [],
            }

        monkeypatch.setattr(
            "services.cm.faq_integration.create_faq_pair_from_livechat",
            _create,
        )
        monkeypatch.setattr(
            "services.faq_entitlements.assert_can_create_faq",
            lambda tenant_id: {"faq_enabled": True},
        )

        response = client.post(
            "/api/faq/create-from-livechat",
            json={
                "question_text": "How much?",
                "answer_text": "Twenty dollars",
                "question_language": "en",
                "tenant_id": "tenant_evil",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body.get("success") is True
        assert body.get("tenant_id") == "tenant_a"
        assert seen.get("tenant_id") == "tenant_a"
