"""Embedded Signup complete: coexistence-only, Graph proof, no leftover credentials."""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import create_engine, select
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
from db.models.whatsapp_cloud import WhatsAppCredential  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.whatsapp_cloud.embedded_signup import (  # noqa: E402
    WhatsAppSignupError,
    complete_embedded_signup,
    start_embedded_signup,
)
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402

WABA = "900100200300"
PHONE = "900100200301"
FINISH = "FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING"


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


def _proven(phone_id: str = PHONE) -> dict[str, Any]:
    return {
        "id": phone_id,
        "display_phone_number": "+20 100 000 2722",
        "verified_name": "Linas Clinic",
        "quality_rating": "GREEN",
        "is_on_biz_app": True,
        "platform_type": "CLOUD_API",
    }


def _debug(waba: str = WABA, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "is_valid": True,
        "app_id": "2963733803971681",
        "expires_at": 0,
        "scopes": ["whatsapp_business_management", "whatsapp_business_messaging"],
        "granular_scopes": [
            {"scope": "whatsapp_business_management", "target_ids": [waba]},
            {"scope": "whatsapp_business_messaging", "target_ids": [waba]},
        ],
    }
    payload.update(overrides)
    return payload


def _mock_graph(monkeypatch, *, phones: list[dict[str, Any]], debug: dict[str, Any] | None = None) -> dict[str, int]:
    calls = {"smb": 0, "exchange": 0}

    async def _exchange(**kwargs: Any) -> dict[str, Any]:
        calls["exchange"] += 1
        return {"access_token": "wa-test-access-token-xxxxxxxxxxxxxxxxxxxx"}

    async def _dbg(**kwargs: Any) -> dict[str, Any]:
        return debug or _debug()

    async def _phones(**kwargs: Any) -> list[dict[str, Any]]:
        return phones

    async def _fields(**kwargs: Any) -> dict[str, Any]:
        pid = str(kwargs.get("phone_number_id") or "")
        for row in phones:
            if str(row.get("id")) == pid:
                return row
        return {"id": pid, "is_on_biz_app": True, "platform_type": "CLOUD_API"}

    async def _sub(**kwargs: Any) -> dict[str, Any]:
        return {"success": True}

    async def _smb(**kwargs: Any) -> dict[str, Any]:
        calls["smb"] += 1
        return {"messaging_product": "whatsapp", "request_id": "req-1"}

    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.exchange_embedded_signup_code", _exchange)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.debug_token", _dbg)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup_proof.fetch_waba_phone_numbers", _phones)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup_proof.fetch_business_phone_number", _fields)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.subscribe_waba_webhooks", _sub)
    monkeypatch.setattr("services.whatsapp_cloud.embedded_signup.initiate_smb_app_data_sync", _smb)
    return calls


def _nonce(tenant: str = "linas") -> str:
    started = start_embedded_signup(tenant_id=tenant, actor_user_id="u1", return_surface="mobile")
    return started["authorization_url"].split("state=")[1].split("&")[0]


def _ok_kwargs(nonce: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "state": nonce,
        "code": "auth-code",
        "waba_id": WABA,
        "phone_number_id": "",
        "session_event": FINISH,
        "session_type": "WA_EMBEDDED_SIGNUP",
        "session_version": "3",
    }
    payload.update(extra)
    return payload


def _cred_count(session) -> int:
    return len(list(session.scalars(select(WhatsAppCredential))))


@pytest.mark.asyncio
async def test_complete_discovers_omitted_phone(wa_db, monkeypatch, tmp_path):
    _grant_linas(monkeypatch, tmp_path, wa_db)
    nonce = _nonce()
    calls = _mock_graph(monkeypatch, phones=[_proven()])
    result = await complete_embedded_signup(**_ok_kwargs(nonce))
    assert result["success"] is True
    assert "access_token" not in str(result)
    repo = WhatsAppCloudRepository(wa_db)
    conns = repo.list_tenant_connections("linas", include_revoked=False)
    assert len(conns) == 1
    assert conns[0].phone_number_id == PHONE
    assert conns[0].display_phone_last4 == "2722"
    assert conns[0].coexistence_mode == "whatsapp_business_app_onboarding"
    assert conns[0].history_sync_status == "pending"
    assert calls["smb"] == 2
    assert calls["exchange"] == 1


@pytest.mark.asyncio
async def test_generic_finish_does_not_create_connection(wa_db, monkeypatch, tmp_path):
    _grant_linas(monkeypatch, tmp_path, wa_db)
    nonce = _nonce()
    calls = _mock_graph(monkeypatch, phones=[_proven()])
    result = await complete_embedded_signup(**_ok_kwargs(nonce, session_event="FINISH", phone_number_id=PHONE))
    assert result["success"] is False
    assert result["error"] == "coexistence_flow_required"
    assert "wa_error=coexistence_flow_required" in result["redirect_url"]
    assert calls["exchange"] == 0
    assert WhatsAppCloudRepository(wa_db).list_tenant_connections("linas", include_revoked=False) == []
    assert _cred_count(wa_db) == 0


@pytest.mark.asyncio
async def test_code_only_and_wrong_session_type_rejected(wa_db, monkeypatch, tmp_path):
    _grant_linas(monkeypatch, tmp_path, wa_db)
    calls = _mock_graph(monkeypatch, phones=[_proven()])
    first = await complete_embedded_signup(
        **_ok_kwargs(_nonce(), session_event="", session_type="", session_version="")
    )
    assert first["error"] == "coexistence_flow_required"
    second = await complete_embedded_signup(
        **_ok_kwargs(_nonce(), session_type="OTHER", session_event=FINISH, session_version="3")
    )
    assert second["error"] == "coexistence_flow_required"
    assert calls["exchange"] == 0
    assert _cred_count(wa_db) == 0


@pytest.mark.asyncio
async def test_graph_and_token_failures_leave_no_credentials(wa_db, monkeypatch, tmp_path):
    _grant_linas(monkeypatch, tmp_path, wa_db)
    _mock_graph(
        monkeypatch,
        phones=[{"id": PHONE, "is_on_biz_app": False, "platform_type": "CLOUD_API", "display_phone_number": "+20100"}],
    )
    result = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert result["error"] == "coexistence_not_proven"
    assert _cred_count(wa_db) == 0

    _mock_graph(monkeypatch, phones=[_proven(), _proven("900100200399")])
    many = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert many["error"] == "coexistence_phone_ambiguous"
    assert _cred_count(wa_db) == 0

    _mock_graph(monkeypatch, phones=[_proven()], debug=_debug(is_valid=False))
    invalid = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert invalid["error"] == "token_invalid"
    assert _cred_count(wa_db) == 0

    _mock_graph(monkeypatch, phones=[_proven()], debug=_debug(app_id="999"))
    wrong_app = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert wrong_app["error"] == "token_wrong_app"

    _mock_graph(monkeypatch, phones=[_proven()], debug=_debug(expires_at=1))
    expired = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert expired["error"] == "token_expired"

    _mock_graph(monkeypatch, phones=[_proven()], debug=_debug(scopes=["email"]))
    scopes = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert scopes["error"] == "scopes_missing"

    _mock_graph(
        monkeypatch,
        phones=[_proven()],
        debug=_debug(granular_scopes=[{"scope": "whatsapp_business_management", "target_ids": ["111"]}]),
    )
    gran = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert gran["error"] == "waba_not_authorized"
    assert WhatsAppCloudRepository(wa_db).list_tenant_connections("linas", include_revoked=False) == []


@pytest.mark.asyncio
async def test_placeholder_cancel_and_existing_connection_untouched(wa_db, monkeypatch, tmp_path):
    with pytest.raises(WhatsAppSignupError) as missing:
        await complete_embedded_signup(state="", code="x", waba_id="1", phone_number_id="2")
    assert missing.value.code == "missing_state"
    with pytest.raises(WhatsAppSignupError) as unknown:
        await complete_embedded_signup(state="unknown-nonce", code="x", waba_id="1", phone_number_id="2")
    assert unknown.value.code == "invalid_state"

    _grant_linas(monkeypatch, tmp_path, wa_db)
    _mock_graph(monkeypatch, phones=[_proven()])
    connected = await complete_embedded_signup(**_ok_kwargs(_nonce()))
    assert connected["success"] is True
    before = WhatsAppCloudRepository(wa_db).list_tenant_connections("linas", include_revoked=False)
    assert len(before) == 1

    nonce = _nonce()
    sample = await complete_embedded_signup(**_ok_kwargs(nonce, phone_number_id="123456123"))
    assert sample["error"] == "sample_phone_forbidden"
    after = WhatsAppCloudRepository(wa_db).list_tenant_connections("linas", include_revoked=False)
    assert [row.id for row in after] == [row.id for row in before]

    cancelled = await complete_embedded_signup(
        **_ok_kwargs(_nonce(), session_event="CANCEL", session_type="WA_EMBEDDED_SIGNUP")
    )
    assert cancelled["success"] is False
    assert "wa_connection=cancelled" in cancelled["redirect_url"]
    still = WhatsAppCloudRepository(wa_db).list_tenant_connections("linas", include_revoked=False)
    assert still[0].lifecycle_status == "connected"


@pytest.mark.asyncio
async def test_other_finish_events_and_timeout_do_not_connect(wa_db, monkeypatch, tmp_path):
    _grant_linas(monkeypatch, tmp_path, wa_db)
    calls = _mock_graph(monkeypatch, phones=[_proven()])
    for event in ("FINISH_ONLY_WABA", "FINISH_GRANT_ONLY_API_ACCESS", "FINISH_OBO_MIGRATION"):
        result = await complete_embedded_signup(**_ok_kwargs(_nonce(), session_event=event))
        assert result["success"] is False
        assert result["error"] == "coexistence_flow_required"
    timeout = await complete_embedded_signup(**_ok_kwargs(_nonce(), code="", error="session_timeout", session_event=""))
    assert timeout["error"] == "session_timeout"
    advanced = await complete_embedded_signup(
        **_ok_kwargs(_nonce(), code="", error="meta_advanced_access_required", session_event="ERROR")
    )
    assert advanced["error"] == "meta_advanced_access_required"
    assert calls["exchange"] == 0
    assert _cred_count(wa_db) == 0
