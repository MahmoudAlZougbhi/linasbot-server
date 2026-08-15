"""WhatsApp Cloud coexistence tests — SQLite SoT (explicit test opt-in)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Force test DB before importing models/session helpers.
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
os.environ["PUBLIC_URL"] = "https://example.test"

from datetime import UTC

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.meta_messaging import verify_meta_signature  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402
from services.whatsapp_cloud.webhook_parser import parse_whatsapp_cloud_payload  # noqa: E402


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    yield session
    session.close()
    reset_engine_for_tests()


def test_phone_number_unique_across_tenants(wa_db):
    repo = WhatsAppCloudRepository(wa_db)
    repo.create_connection_with_credential(
        tenant_id="tenant_a",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="999001",
        display_phone_number="+96171111111",
        verified_name="A",
        access_token="token-a",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    wa_db.commit()
    with pytest.raises(PermissionError, match="phone_number_owned_by_other_tenant"):
        repo.create_connection_with_credential(
            tenant_id="tenant_b",
            created_by_user_id="u2",
            meta_app_key="linas_first_party",
            meta_app_id="2963733803971681",
            waba_id="222",
            phone_number_id="999001",
            display_phone_number="+96172222222",
            verified_name="B",
            access_token="token-b",
            scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
        )


def test_credential_encrypted_not_plaintext(wa_db):
    repo = WhatsAppCloudRepository(wa_db)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_a",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="999002",
        display_phone_number="+96171111112",
        verified_name="A",
        access_token="super-secret-token",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    wa_db.commit()
    from db.models.whatsapp_cloud import WhatsAppCredential

    cred = wa_db.get(WhatsAppCredential, conn.credential_id)
    assert cred is not None
    assert "super-secret-token" not in cred.ciphertext
    assert cred.ciphertext.startswith("v1.")
    assert repo.load_access_token(conn) == "super-secret-token"


def test_webhook_signature_valid_invalid_missing():
    body = b'{"object":"whatsapp_business_account"}'
    secret = "test-app-a-secret"
    sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_meta_signature(body, sig, secret) is True
    assert verify_meta_signature(body, "sha256=deadbeef", secret) is False
    assert verify_meta_signature(body, None, secret) is False
    assert verify_meta_signature(body, sig, "") is False


def test_parse_inbound_echo_history_status():
    inbound = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "pn1"},
                            "contacts": [{"profile": {"name": "Cus"}}],
                            "messages": [
                                {
                                    "from": "96170000000",
                                    "id": "wamid.IN1",
                                    "timestamp": "1",
                                    "type": "text",
                                    "text": {"body": "hello"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    events = parse_whatsapp_cloud_payload(inbound)
    assert len(events) == 1
    assert events[0].event_kind == "inbound_message"
    assert events[0].text_body == "hello"

    echo = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba1",
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "metadata": {"phone_number_id": "pn1"},
                            "message_echoes": [{"id": "wamid.ECHO1", "to": "96170000000", "type": "text"}],
                        },
                    }
                ],
            }
        ],
    }
    echoes = parse_whatsapp_cloud_payload(echo)
    assert echoes[0].event_kind == "smb_message_echoes"

    history = {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "waba1", "changes": [{"field": "history", "value": {"metadata": {"phone_number_id": "pn1"}}}]}
        ],
    }
    hist = parse_whatsapp_cloud_payload(history)
    assert hist[0].event_kind == "history"


@pytest.mark.asyncio
async def test_echo_pauses_and_inbound_ai_once(wa_db, monkeypatch):
    from services.whatsapp_cloud import webhook_processor as wp

    repo = WhatsAppCloudRepository(wa_db)
    repo.grant_pilot(tenant_id="tenant_a", granted_by_user_id="po", reason="test pilot")
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_a",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="pn_echo",
        display_phone_number="+96171111999",
        verified_name="Shop",
        access_token="tok",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["messages", "smb_message_echoes"])
    conn.ai_default_enabled = True
    conn.history_sync_status = "skipped"
    wa_db.commit()

    calls: list[dict[str, Any]] = []

    async def fake_ai(snapshot):
        calls.append(dict(snapshot))

    monkeypatch.setattr(wp, "maybe_generate_and_send_ai_reply", fake_ai)
    monkeypatch.setattr(wp, "evaluate_ai_eligibility", lambda session, c: (True, None))

    # Manual echo → pause, no AI
    echo_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "111",
                "changes": [
                    {
                        "field": "smb_message_echoes",
                        "value": {
                            "metadata": {"phone_number_id": "pn_echo"},
                            "message_echoes": [{"id": "wamid.E1", "to": "96170000001", "type": "text"}],
                        },
                    }
                ],
            }
        ],
    }
    # Rebind whatsapp_session to our test session
    from contextlib import contextmanager

    @contextmanager
    def _sess(*, require: bool = True):
        yield wa_db
        wa_db.commit()

    monkeypatch.setattr(wp, "whatsapp_session", _sess)
    monkeypatch.setattr("services.whatsapp_cloud.ai_bridge.whatsapp_session", _sess)

    r1 = await wp.process_whatsapp_cloud_webhook(raw_body=json.dumps(echo_payload).encode(), payload=echo_payload)
    assert r1["accepted"] >= 1
    assert calls == []
    conv = repo.get_or_create_conversation(tenant_id="tenant_a", connection_id=conn.id, customer_wa_id="96170000001")
    assert conv.control_state == "HUMAN_PAUSED"

    inbound = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "111",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "pn_echo"},
                            "messages": [
                                {
                                    "from": "96170000001",
                                    "id": "wamid.I1",
                                    "type": "text",
                                    "text": {"body": "hi again"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    r2 = await wp.process_whatsapp_cloud_webhook(raw_body=json.dumps(inbound).encode(), payload=inbound)
    assert r2["accepted"] >= 1
    assert calls == []  # still paused

    # Resume then inbound triggers AI once
    repo.resume_conversation(conv, actor_user_id="u1")
    wa_db.commit()
    inbound2 = json.loads(json.dumps(inbound))
    inbound2["entry"][0]["changes"][0]["value"]["messages"][0]["id"] = "wamid.I2"
    r3 = await wp.process_whatsapp_cloud_webhook(raw_body=json.dumps(inbound2).encode(), payload=inbound2)
    assert r3["accepted"] >= 1
    assert len(calls) == 1

    # Duplicate inbound suppressed
    r4 = await wp.process_whatsapp_cloud_webhook(raw_body=json.dumps(inbound2).encode(), payload=inbound2)
    assert r4["duplicates"] >= 1
    assert len(calls) == 1


def test_concurrent_duplicate_inbound_claims(wa_db, monkeypatch):
    repo = WhatsAppCloudRepository(wa_db)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_a",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="pn_conc",
        display_phone_number="+96171111888",
        verified_name="Shop",
        access_token="tok",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["messages"])
    wa_db.commit()

    def claim_once(i: int) -> bool:
        # Each thread needs its own session against same DB file.
        engine = wa_db.get_bind()
        Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
        s = Session()
        try:
            r = WhatsAppCloudRepository(s)
            _event, is_new = r.claim_webhook_event(
                event_key="inbound:wamid.SAME",
                event_kind="inbound_message",
                payload_hash="abc",
                tenant_id="tenant_a",
                connection_id=conn.id,
            )
            s.commit()
            return is_new
        finally:
            s.close()

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(claim_once, range(100)))
    assert sum(1 for x in results if x) == 1
    assert sum(1 for x in results if not x) == 99


def test_attempt_state_replay_and_expiry(wa_db):
    from datetime import datetime, timedelta

    repo = WhatsAppCloudRepository(wa_db)
    attempt, nonce = repo.create_connection_attempt(
        tenant_id="tenant_a",
        actor_user_id="u1",
        return_surface="mobile",
        meta_app_key="linas_first_party",
        ttl_seconds=1,
    )
    state_hash = hashlib.sha256(nonce.encode()).hexdigest()
    loaded = repo.get_attempt_by_state_hash(state_hash)
    assert loaded is not None
    repo.consume_attempt(loaded, outcome_code="ok", status="consumed")
    with pytest.raises(ValueError, match="attempt_not_pending"):
        repo.consume_attempt(loaded, outcome_code="again")

    attempt2, nonce2 = repo.create_connection_attempt(
        tenant_id="tenant_a",
        actor_user_id="u1",
        return_surface="mobile",
        meta_app_key="linas_first_party",
        ttl_seconds=600,
    )
    attempt2.expires_at = datetime.now(UTC) - timedelta(seconds=5)
    wa_db.flush()
    with pytest.raises(ValueError, match="attempt_expired"):
        repo.consume_attempt(attempt2, outcome_code="late")


def test_history_events_never_create_outbound_intent(wa_db, monkeypatch):
    from contextlib import contextmanager

    from services.whatsapp_cloud import webhook_processor as wp

    repo = WhatsAppCloudRepository(wa_db)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_a",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="pn_hist",
        display_phone_number="+96171111777",
        verified_name="Shop",
        access_token="tok",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["history"])
    wa_db.commit()

    @contextmanager
    def _sess(*, require: bool = True):
        yield wa_db
        wa_db.commit()

    monkeypatch.setattr(wp, "whatsapp_session", _sess)

    import asyncio

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {"id": "111", "changes": [{"field": "history", "value": {"metadata": {"phone_number_id": "pn_hist"}}}]}
        ],
    }
    result = asyncio.get_event_loop().run_until_complete(
        wp.process_whatsapp_cloud_webhook(raw_body=json.dumps(payload).encode(), payload=payload)
    )
    assert result["accepted"] >= 1
    from sqlalchemy import select

    from db.models.whatsapp_cloud import WhatsAppOutboundIntent

    intents = wa_db.scalars(select(WhatsAppOutboundIntent)).all()
    assert intents == []


def test_mobile_deep_link_never_operator_login():
    from services.meta_oauth_return import oauth_completion_redirect_url

    url = oauth_completion_redirect_url(return_surface="mobile", meta_connection="success")
    assert url.startswith("linasai://integrations")
    assert "/settings" not in url
    assert "login" not in url.lower()


def test_config_key_presence_has_no_values():
    from services.whatsapp_cloud.config import whatsapp_config_key_presence

    presence = whatsapp_config_key_presence()
    assert isinstance(presence, dict)
    assert all(isinstance(v, bool) for v in presence.values())
    assert "WHATSAPP_CLOUD_PUBLIC_AVAILABILITY" in presence


def _grant_whatsapp_plan(monkeypatch, tmp_path, tenant_id: str, plan_id: str = "starter") -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.membership import whatsapp_gate as wg

    store = EntitlementsStore(root=tmp_path / "ent-wa-plan")
    monkeypatch.setattr(es, "entitlements_store", store)
    monkeypatch.setattr(wg, "entitlements_store", store)
    monkeypatch.setenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", "linas")
    store.set_plan(tenant_id=tenant_id, plan_id=plan_id, status="active", source="admin")


def test_public_availability_skips_pilot(monkeypatch, wa_db, tmp_path):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "true")
    monkeypatch.setenv("WHATSAPP_CLOUD_CONNECTION_UI_ENABLED", "false")
    from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
    from services.whatsapp_cloud.entitlement import assert_whatsapp_connection_allowed

    _grant_whatsapp_plan(monkeypatch, tmp_path, "any_tenant")
    flags = get_whatsapp_cloud_flags()
    assert flags.public_availability is True
    assert flags.require_pilot_entitlement is False
    # Should not raise even without pilot row when public switch is on.
    assert_whatsapp_connection_allowed(wa_db, "any_tenant")


def test_pilot_required_when_public_off(monkeypatch, wa_db, tmp_path):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.setenv("WHATSAPP_CLOUD_CONNECTION_UI_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT", "true")
    from services.whatsapp_cloud.entitlement import WhatsAppEntitlementError, assert_whatsapp_connection_allowed

    _grant_whatsapp_plan(monkeypatch, tmp_path, "no_pilot_tenant")
    try:
        assert_whatsapp_connection_allowed(wa_db, "no_pilot_tenant")
        raise AssertionError("expected WHATSAPP_PILOT_REQUIRED")
    except WhatsAppEntitlementError as exc:
        assert exc.code == "WHATSAPP_PILOT_REQUIRED"


def test_grant_pilot_enables_connect(monkeypatch, wa_db, tmp_path):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.setenv("WHATSAPP_CLOUD_CONNECTION_UI_ENABLED", "true")
    from services.whatsapp_cloud.entitlement import assert_whatsapp_connection_allowed
    from services.whatsapp_cloud.repository import WhatsAppCloudRepository

    _grant_whatsapp_plan(monkeypatch, tmp_path, "pilot_t")
    repo = WhatsAppCloudRepository(wa_db)
    repo.grant_pilot(tenant_id="pilot_t", granted_by_user_id="owner", reason="internal film")
    wa_db.commit()
    assert_whatsapp_connection_allowed(wa_db, "pilot_t")
    assert repo.list_pilots(status="active")[0].tenant_id == "pilot_t"
