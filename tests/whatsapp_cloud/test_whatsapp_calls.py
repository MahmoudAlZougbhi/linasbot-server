"""WhatsApp Call enable/disable stores intent on the connection."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

os.environ.setdefault("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
os.environ.setdefault("META_CREDENTIAL_ENCRYPTION_KEY", "z" * 32)
os.environ.setdefault("META_APP_A_ID", "2963733803971681")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "pytest-dashboard-secret")


@pytest.fixture()
def calls_api(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'wa_calls.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", database_url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")

    from db.models import Base
    from db.session import reset_engine_for_tests, whatsapp_session
    from services.dashboard_session_service import session_service
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    reset_engine_for_tests()
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with whatsapp_session() as db:
        repo = WhatsAppCloudRepository(db)
        connection = repo.create_connection_with_credential(
            tenant_id="linas",
            created_by_user_id="ops-user",
            meta_app_key="linas_first_party",
            meta_app_id="2963733803971681",
            waba_id="waba-calls",
            phone_number_id="phone-calls",
            display_phone_number="+1 555 673 4285",
            verified_name="Test Number",
            access_token="ops-token",
            scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
        )
        repo.mark_connection_connected(connection, webhook_fields=["messages"])
        connection_id = connection.id
        assert connection.calls_enabled is False

    import modules.whatsapp_cloud_calls_api  # noqa: F401
    from modules.core import app

    session = session_service.create_session(
        user_id="ops-user",
        email="ops@example.com",
        role="admin",
        permissions=None,
        tenant_id="linas",
    )
    headers = {"Authorization": f"Bearer {session_service.cookie_value_for(session)}"}

    with TestClient(app) as client:
        yield client, connection_id, headers

    reset_engine_for_tests()


def test_calls_default_off_then_enable_disable(calls_api):
    client, connection_id, headers = calls_api

    enabled = client.post(
        f"/api/whatsapp/cloud/connections/{connection_id}/calls/enable",
        headers=headers,
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["connection"]["calls_enabled"] is True

    disabled = client.post(
        f"/api/whatsapp/cloud/connections/{connection_id}/calls/disable",
        headers=headers,
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["connection"]["calls_enabled"] is False


def test_calls_unknown_connection_404(calls_api):
    client, _connection_id, headers = calls_api
    response = client.post(
        "/api/whatsapp/cloud/connections/missing/calls/enable",
        headers=headers,
    )
    assert response.status_code == 404
