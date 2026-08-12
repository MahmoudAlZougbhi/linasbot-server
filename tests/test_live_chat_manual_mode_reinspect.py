"""Phase 11 live-chat manual-mode reinspection: actor attribution + image send honesty."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from services.dashboard_session_service import CSRF_COOKIE_NAME, SESSION_COOKIE_NAME, session_service
from services.live_chat_service import live_chat_service

_ROUTE_MODULES = ("modules.live_chat_api",)


@pytest.fixture(scope="module")
def client() -> TestClient:
    os.environ.setdefault("LINASLASER_API_BASE_URL", "https://example.com")
    os.environ.setdefault("LINASLASER_API_TOKEN", "test-token")
    os.environ.setdefault("DASHBOARD_AUTH_SECRET", "live-chat-manual-reinspect-secret")
    os.environ["ENVIRONMENT"] = "test"
    os.environ.setdefault("DISABLE_API_DOCS", "true")
    for mod in _ROUTE_MODULES:
        __import__(mod)
    from modules.core import app

    return TestClient(app)


def _set_session(client: TestClient, *, user_id: str = "op-real") -> None:
    client.cookies.clear()
    rec = session_service.create_session(
        user_id=user_id,
        email=f"{user_id}@example.com",
        role="admin",
        permissions=None,
        tenant_id="linas",
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
    client.headers.update({"X-CSRF-Token": rec.csrf_token})


def test_operator_status_uses_session_actor_not_body(client: TestClient) -> None:
    _set_session(client, user_id="session-op")
    with patch.object(live_chat_service, "update_operator_status", new_callable=AsyncMock) as mock_upd:
        mock_upd.return_value = {"success": True, "operator_id": "session-op", "status": "busy"}
        r = client.post(
            "/api/live-chat/operator-status",
            json={"operator_id": "spoofed-other-op", "status": "busy"},
        )
    assert r.status_code == 200
    mock_upd.assert_awaited_once()
    kwargs = mock_upd.await_args.kwargs
    assert kwargs["operator_id"] == "session-op"
    assert kwargs["status"] == "busy"


@pytest.mark.asyncio
async def test_image_send_reports_failure_when_adapter_fails() -> None:
    adapter = MagicMock()
    adapter.send_image_message = AsyncMock(return_value={"success": False, "error": "provider_down"})
    pause_result = MagicMock(activated=True, already_active=False, control_epoch=None)

    with (
        patch(
            "services.live_chat_service_operator._try_acquire_operator_send_idempotency",
            new_callable=AsyncMock,
            return_value=(True, None),
        ),
        patch("services.live_chat_service_operator._release_operator_idempotency_lock", new_callable=AsyncMock),
        patch("utils.utils.get_canonical_user_id_and_phone", return_value=("user1", "+961")),
        patch("utils.utils.get_firestore_db", return_value=None),
        patch("utils.utils.save_conversation_message_to_firestore", new_callable=AsyncMock),
        patch("utils.utils.upload_base64_to_firebase_storage", new_callable=AsyncMock, return_value="https://cdn/x.jpg"),
        patch(
            "services.requests.manual_mode.activate_manual_mode",
            new_callable=AsyncMock,
            return_value=pause_result,
        ),
    ):
        result = await live_chat_service.send_operator_message(
            conversation_id="c1",
            user_id="user1",
            message="YmFzZTY0",
            operator_id="op1",
            adapter=adapter,
            message_type="image",
            tenant_id=None,
        )
    assert result.get("success") is False
    assert "provider_down" in str(result.get("error", ""))
