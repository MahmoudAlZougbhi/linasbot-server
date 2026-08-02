"""Testing Lab Meta social path: capture-only, no Firestore/outbound Graph."""

from __future__ import annotations

from unittest import mock

import pytest
from fastapi.testclient import TestClient

from services.dashboard_session_service import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, SESSION_COOKIE_NAME, session_service
from services.meta_messaging import MetaMessagingSettings


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "test-dashboard-secret-for-lab")
    monkeypatch.setenv("ENVIRONMENT", "test")
    import modules.dashboard_api  # noqa: F401
    from modules.core import app

    return TestClient(app)


def _set_admin(client: TestClient) -> None:
    rec = session_service.create_session(
        user_id="lab-admin",
        email="lab-admin@example.com",
        role="admin",
        permissions={"testing": True, "liveChat": True},
        password_epoch=0,
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
    client.headers[CSRF_HEADER_NAME] = rec.csrf_token


@pytest.mark.parametrize("channel", ["instagram", "facebook"])
def test_lab_meta_social_returns_captured_reply_without_firestore_or_graph(
    client: TestClient, channel: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_admin(client)
    settings = MetaMessagingSettings(
        enabled=True,
        app_secret="secret",
        page_id="378696005334409",
        page_access_token="page-token",
        instagram_account_id="17841413184256533",
        verify_token="verify",
        graph_api_version="v24.0",
    )
    monkeypatch.setattr(
        "modules.dashboard_api.get_meta_messaging_settings",
        lambda: settings,
        raising=False,
    )
    monkeypatch.setattr(
        "services.meta_messaging.get_meta_messaging_settings",
        lambda: settings,
    )

    class FakeAdapter:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("MetaMessagingAdapter must not be constructed in simulation")

    monkeypatch.setattr(
        "services.social_messaging_processor.MetaMessagingAdapter",
        FakeAdapter,
    )

    save_mock = mock.AsyncMock()
    monkeypatch.setattr(
        "utils.utils.save_conversation_message_to_firestore",
        save_mock,
        raising=False,
    )

    async def fake_handle_message(**kwargs: object) -> None:
        assert kwargs.get("skip_firestore_save") is True
        send = kwargs["send_message_func"]
        await send(kwargs["user_id"], "Lab canonical reply")

    monkeypatch.setattr(
        "services.social_messaging_processor.handle_message",
        fake_handle_message,
    )

    # Session validation may look up the user; keep auth path offline-safe.
    monkeypatch.setattr(
        "services.user_service.user_service.get_user_by_id",
        lambda _uid: {
            "id": "lab-admin",
            "email": "lab-admin@example.com",
            "role": "admin",
            "status": "active",
            "permissions": {"testing": True},
            "passwordEpoch": 0,
        },
        raising=False,
    )

    response = client.post(
        "/api/test-message",
        json={
            "phone": "123456789",
            "message": "Hello",
            "provider": "montymobile",
            "channel": channel,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] is True, body
    assert body["simulation"] is True
    assert body["external_delivery"] is False
    assert body["parity_mode"] == "meta_social"
    assert body["channel"] == channel
    assert body["bot_response"] == "Lab canonical reply"
    assert save_mock.await_count == 0
