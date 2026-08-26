"""Redacted App Review readiness, bind dry-run, webhook HTTP, outbound retry."""

from __future__ import annotations

import hashlib
import hmac
import os
from contextlib import contextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ["META_CREDENTIAL_ENCRYPTION_KEY"] = "x" * 32
os.environ["META_APP_A_ID"] = "2963733803971681"
os.environ["META_APP_A_SECRET"] = "test-app-a-secret"
os.environ["META_APP_A_WEBHOOK_VERIFY_TOKEN"] = "test-verify-token"
os.environ["META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID"] = "es-config-test"
os.environ["WHATSAPP_CLOUD_CONNECTION_UI_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_AI_REPLIES_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] = "false"
os.environ["PUBLIC_URL"] = "https://example.test"
os.environ["DASHBOARD_AUTH_SECRET"] = "pytest-dashboard-secret"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.whatsapp_cloud.app_review_bind import bind_app_review_test_number  # noqa: E402
from services.whatsapp_cloud.app_review_readiness import (  # noqa: E402
    build_app_review_readiness,
    whatsapp_rollout_fingerprint,
)
from services.whatsapp_cloud.redaction import redact_whatsapp_text  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402

TEST_WABA = "900100200300"
TEST_PHONE = "900100200301"
TEST_TOKEN = "EAAG-test-token-never-log-" + ("y" * 40)


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_ready.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_BIND_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()

    @contextmanager
    def _sess(*, require: bool = True):
        yield session
        session.commit()

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind.whatsapp_session", _sess)
    monkeypatch.setattr("services.whatsapp_cloud.app_review_readiness.whatsapp_session", _sess)
    yield session
    session.close()
    reset_engine_for_tests()


def _mock_meta_ok(monkeypatch) -> None:
    async def _debug(**kwargs: Any) -> dict[str, Any]:
        return {
            "is_valid": True,
            "app_id": "2963733803971681",
            "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
        }

    async def _phones(**kwargs: Any) -> list[dict[str, Any]]:
        return [{"id": TEST_PHONE, "display_phone_number": "+1 555 010 1234", "verified_name": "Linas Test"}]

    async def _sub(**kwargs: Any) -> dict[str, Any]:
        return {"success": True}

    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.debug_token", _debug)
    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind_helpers.fetch_waba_phone_numbers", _phones)
    monkeypatch.setattr("services.whatsapp_cloud.app_review_bind.subscribe_waba_webhooks", _sub)


def test_readiness_redacted_and_public_false(wa_db, monkeypatch):
    payload = build_app_review_readiness(tenant_id="linas")
    assert payload["success"] is True
    assert payload["public_availability"] is False
    assert payload["flags"]["public_availability"] is False
    assert payload["coexistence_feature"] == "whatsapp_business_app_onboarding"
    blob = str(payload)
    assert TEST_TOKEN not in blob
    assert "EAAG" not in blob
    assert payload["config_keys_present"]["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] is True
    fp1 = whatsapp_rollout_fingerprint()
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "true")
    fp2 = whatsapp_rollout_fingerprint()
    assert fp1 != fp2
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    assert whatsapp_rollout_fingerprint() == fp1


def test_redaction_masks_tokens_and_long_numbers() -> None:
    text = redact_whatsapp_text("token=EAAGSECRETTOKEN123 dest=201000002722")
    assert "EAAGSECRETTOKEN123" not in text
    assert "[redacted-token]" in text
    assert "2722" in text
    assert "201000002722" not in text


@pytest.mark.asyncio
async def test_bind_dry_run_does_not_persist(wa_db, monkeypatch):
    _mock_meta_ok(monkeypatch)
    result = await bind_app_review_test_number(
        tenant_id="linas",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        access_token=None,
        actor_user_id="po1",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.action == "dry_run"
    assert result.display_phone_last4 == "1234"
    repo = WhatsAppCloudRepository(wa_db)
    assert repo.list_tenant_connections("linas") == []


def test_readiness_and_webhook_http_auth(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_http.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    import modules.whatsapp_cloud_api  # noqa: F401
    import modules.whatsapp_cloud_ops_api  # noqa: F401
    import modules.whatsapp_cloud_webhook  # noqa: F401
    from modules.core import app

    with TestClient(app) as client:
        ready = client.get("/api/whatsapp/cloud/app-review/readiness")
        assert ready.status_code in {401, 403}
        bind = client.post("/api/whatsapp/cloud/app-review/bind", json={"tenant_id": "linas", "dry_run": True})
        assert bind.status_code in {401, 403}
        body = b'{"object":"whatsapp_business_account"}'
        denied = client.post("/webhook/whatsapp-cloud", content=body)
        assert denied.status_code == 403
        sig = "sha256=" + hmac.new(b"test-app-a-secret", body, hashlib.sha256).hexdigest()
        accepted = client.post("/webhook/whatsapp-cloud", content=body, headers={"X-Hub-Signature-256": sig})
        assert accepted.status_code == 200
        bridge = client.get("/integrations/whatsapp/embedded-signup?state=x&config_id=cfg")
        assert bridge.status_code == 200
        assert "whatsapp_business_app_onboarding" in bridge.text
        assert "Do not choose Add a new number" in bridge.text
    reset_engine_for_tests()


@pytest.mark.asyncio
async def test_outbound_retry_after_failure(wa_db, monkeypatch):
    from services.whatsapp_cloud import delivery_retry as dr
    from services.whatsapp_cloud.graph_client import WhatsAppGraphError

    repo = WhatsAppCloudRepository(wa_db)
    conn = repo.create_connection_with_credential(
        tenant_id="linas",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        display_phone_number="+1 555 010 1234",
        verified_name="Linas Test",
        access_token="tok",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["messages"])
    conv = repo.get_or_create_conversation(tenant_id="linas", connection_id=conn.id, customer_wa_id="15551230000")
    intent, created = repo.create_outbound_intent(
        tenant_id="linas",
        connection_id=conn.id,
        conversation_id=conv.id,
        idempotency_key="retry-1",
        control_epoch=0,
        triggering_inbound_message_id=None,
    )
    assert created is True
    intent.canonical_text = "hello"
    intent.dispatch_state = "failed"
    wa_db.commit()

    @contextmanager
    def _sess(*, require: bool = True):
        yield wa_db
        wa_db.commit()

    monkeypatch.setattr(dr, "whatsapp_session", _sess)
    sends = {"n": 0}

    async def _send(**kwargs: Any) -> dict[str, Any]:
        sends["n"] += 1
        if sends["n"] == 1:
            raise WhatsAppGraphError("meta_1", "temporary", http_status=500, retryable=True)
        return {"messages": [{"id": "wamid.ok"}]}

    monkeypatch.setattr(dr, "send_text_message", _send)
    first = await dr.send_canonical_intent(intent.id)
    assert first["ok"] is False
    second = await dr.send_canonical_intent(intent.id)
    assert second["ok"] is True
    assert second["wamid"] == "wamid.ok"
