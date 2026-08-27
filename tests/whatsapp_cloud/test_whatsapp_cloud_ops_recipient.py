"""Server-side recipient validation for the WhatsApp Cloud test-send API."""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

os.environ.setdefault("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
os.environ.setdefault("META_CREDENTIAL_ENCRYPTION_KEY", "z" * 32)
os.environ.setdefault("META_APP_A_ID", "2963733803971681")
os.environ.setdefault("DASHBOARD_AUTH_SECRET", "pytest-dashboard-secret")
os.environ.setdefault("WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED", "true")


@pytest.fixture()
def ops_api(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'wa_ops_recipient.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", database_url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED", "true")

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
            waba_id="waba-ops",
            phone_number_id="phone-ops",
            display_phone_number="+1 555 673 4285",
            verified_name="Test Number",
            access_token="ops-token",
            scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
        )
        repo.mark_connection_connected(connection, webhook_fields=["messages"])
        connection_id = connection.id

    import modules.whatsapp_cloud_ops_api as ops
    from modules.core import app

    graph_calls: list[dict[str, Any]] = []

    async def _send_text_message(**kwargs: Any) -> dict[str, Any]:
        graph_calls.append(kwargs)
        return {"messages": [{"id": "wamid.test"}]}

    monkeypatch.setattr(ops, "send_text_message", _send_text_message)
    session = session_service.create_session(
        user_id="ops-user",
        email="ops@example.com",
        role="admin",
        permissions=None,
        tenant_id="linas",
    )
    headers = {"Authorization": f"Bearer {session_service.cookie_value_for(session)}"}

    with TestClient(app) as client:
        yield client, connection_id, headers, graph_calls

    reset_engine_for_tests()


@pytest.mark.parametrize("recipient", ["03956607", "+961 3 956 60O", "call +961 3 956 607", "961.395.6607"])
def test_test_message_rejects_local_or_garbage_recipient(ops_api, recipient):
    client, connection_id, headers, graph_calls = ops_api

    response = client.post(
        f"/api/whatsapp/cloud/connections/{connection_id}/test-message",
        headers=headers,
        json={"to_wa_id": recipient, "text": "Hello"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "to_wa_id_required"
    assert graph_calls == []


def test_test_message_normalizes_safe_international_format_before_graph(ops_api):
    client, connection_id, headers, graph_calls = ops_api

    response = client.post(
        f"/api/whatsapp/cloud/connections/{connection_id}/test-message",
        headers=headers,
        json={"to_wa_id": "+961 3 956 607", "text": "Hello"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["to_wa_id_masked"] == "…6607"
    assert len(graph_calls) == 1
    assert graph_calls[0]["to_wa_id"] == "9613956607"
