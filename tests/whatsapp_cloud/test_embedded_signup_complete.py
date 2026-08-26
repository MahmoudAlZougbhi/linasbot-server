"""Embedded Signup complete path: OAuth state, omitted phone, placeholders."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ["META_CREDENTIAL_ENCRYPTION_KEY"] = "x" * 32
os.environ["META_APP_A_ID"] = "2963733803971681"
os.environ["META_APP_A_SECRET"] = "test-app-a-secret"
os.environ["META_APP_A_WEBHOOK_VERIFY_TOKEN"] = "test-verify-token"
os.environ["META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID"] = "es-config-test"
os.environ["WHATSAPP_CLOUD_CONNECTION_UI_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] = "false"
os.environ["PUBLIC_URL"] = "https://example.test"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.whatsapp_cloud.embedded_signup import (  # noqa: E402
    WhatsAppSignupError,
    complete_embedded_signup,
    start_embedded_signup,
)
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_complete.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.setenv("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", "true")
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()

    @contextmanager
    def _sess(*, require: bool = True):
        yield session
        session.commit()

    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.whatsapp_session", _sess)
    yield session
    session.close()
    reset_engine_for_tests()


def _grant_linas(monkeypatch, tmp_path, session) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import whatsapp_gate as wg

    store = EntitlementsStore(root=tmp_path / "ent-complete")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(wg, "entitlements_store", store)
    repo = WhatsAppCloudRepository(session)
    repo.grant_pilot(tenant_id="linas", granted_by_user_id="po", reason="test")
    session.commit()


def _mock_graph(monkeypatch, *, phones: list[dict[str, Any]]) -> dict[str, int]:
    calls = {"smb": 0}

    async def _exchange(**kwargs: Any) -> dict[str, Any]:
        return {"access_token": "EAAGtesttokenxxxxxxxxxxxxxxxxxxxx"}

    async def _debug(**kwargs: Any) -> dict[str, Any]:
        return {
            "is_valid": True,
            "app_id": "2963733803971681",
            "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
        }

    async def _phones(**kwargs: Any) -> list[dict[str, Any]]:
        return phones

    async def _sub(**kwargs: Any) -> dict[str, Any]:
        return {"success": True}

    async def _smb(**kwargs: Any) -> dict[str, Any]:
        calls["smb"] += 1
        return {"messaging_product": "whatsapp", "request_id": "req-1"}

    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.exchange_embedded_signup_code", _exchange)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.debug_token", _debug)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.fetch_waba_phone_numbers", _phones)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.subscribe_waba_webhooks", _sub)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.initiate_smb_app_data_sync", _smb)
    return calls


@pytest.mark.asyncio
async def test_complete_discovers_omitted_phone(wa_db, monkeypatch, tmp_path):
    _grant_linas(monkeypatch, tmp_path, wa_db)
    started = start_embedded_signup(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    nonce = started["authorization_url"].split("state=")[1].split("&")[0]
    calls = _mock_graph(
        monkeypatch,
        phones=[
            {
                "id": "900100200301",
                "display_phone_number": "+20 100 000 2722",
                "verified_name": "Linas Clinic",
                "is_on_biz_app": True,
                "platform_type": "CLOUD_API",
            }
        ],
    )
    result = await complete_embedded_signup(
        state=nonce,
        code="auth-code",
        waba_id="900100200300",
        phone_number_id="",
        session_event="FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING",
    )
    assert result["success"] is True
    repo = WhatsAppCloudRepository(wa_db)
    conns = repo.list_tenant_connections("linas", include_revoked=False)
    assert len(conns) == 1
    assert conns[0].phone_number_id == "900100200301"
    assert conns[0].display_phone_last4 == "2722"
    assert conns[0].history_sync_status == "pending"
    assert calls["smb"] == 2


@pytest.mark.asyncio
async def test_complete_rejects_placeholder_and_missing_state(wa_db, monkeypatch, tmp_path):
    with pytest.raises(WhatsAppSignupError) as missing:
        await complete_embedded_signup(state="", code="x", waba_id="1", phone_number_id="2")
    assert missing.value.code == "missing_state"

    _grant_linas(monkeypatch, tmp_path, wa_db)
    started = start_embedded_signup(tenant_id="linas", actor_user_id="u1", return_surface="web")
    nonce = started["authorization_url"].split("state=")[1].split("&")[0]
    _mock_graph(monkeypatch, phones=[{"id": "900100200301", "display_phone_number": "+1 555 010 1234"}])
    with pytest.raises(WhatsAppSignupError) as exc:
        await complete_embedded_signup(
            state=nonce,
            code="auth-code",
            waba_id="900100200300",
            phone_number_id="123456123",
        )
    assert exc.value.code == "sample_phone_forbidden"


@pytest.mark.asyncio
async def test_complete_invalid_state_and_cancel_event(wa_db, monkeypatch, tmp_path):
    with pytest.raises(WhatsAppSignupError) as exc:
        await complete_embedded_signup(state="unknown-nonce", code="x", waba_id="1", phone_number_id="2")
    assert exc.value.code == "invalid_state"

    _grant_linas(monkeypatch, tmp_path, wa_db)
    started = start_embedded_signup(tenant_id="linas", actor_user_id="u1", return_surface="mobile")
    nonce = started["authorization_url"].split("state=")[1].split("&")[0]
    result = await complete_embedded_signup(
        state=nonce,
        code="auth-code",
        waba_id="900100200300",
        phone_number_id="900100200301",
        session_event="CANCEL",
    )
    assert result["success"] is False
    assert "wa_connection=cancelled" in result["redirect_url"]
