"""Website Chat containment gate tests (default OFF until Meta App Review).

Full Web Chat redesign is deferred until after Meta App Review.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ["META_CREDENTIAL_ENCRYPTION_KEY"] = "x" * 32

from db.models import Base  # noqa: E402
from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.constants import (  # noqa: E402
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_WEB_CHAT,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)
from services.smart_followup.adapters.web import WebFollowUpAdapter  # noqa: E402
from services.smart_followup.hooks import schedule_after_ai_reply  # noqa: E402
from services.smart_followup.settings_service import update_settings  # noqa: E402
from services.smart_followup.types import FollowUpConversationView  # noqa: E402
from services.web_chat.flags import PUBLIC_AVAILABILITY_ENV, flags_snapshot  # noqa: E402
from services.web_chat.store import WebChatStore  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402


@pytest.fixture()
def web_store(tmp_path, monkeypatch):
    store = WebChatStore(root=tmp_path / "web_chat")
    monkeypatch.setattr("services.web_chat.store.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_helpers.web_chat_store", store)
    monkeypatch.setattr("modules.web_chat_public_routes.web_chat_store", store)
    return store


@pytest.fixture()
def contained_client(monkeypatch, web_store):
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore

    ent = EntitlementsStore(root=web_store._root.parent / "ent")
    monkeypatch.setattr(es, "entitlements_store", ent)
    ent.set_plan(tenant_id="biz", plan_id="max", status="active", source="admin")

    from main import app

    return TestClient(app)


@pytest.fixture()
def sfu_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'sfu_contain.db'}"
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


def _seed_widget(store: WebChatStore) -> str:
    widget = store.update_widget(
        "biz",
        site_url="https://shop.example.com",
        enabled=True,
        integration_mode="linas_widget",
    )
    return widget.widget_key


def test_flags_default_off_and_meta_review_note(monkeypatch) -> None:
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    snapshot = flags_snapshot()
    assert snapshot[PUBLIC_AVAILABILITY_ENV] is False
    assert snapshot["web_chat_containment_active"] is True
    assert "Meta App Review" in str(snapshot["meta_app_review_note"])


def test_public_endpoints_closed_when_gate_off(contained_client, web_store) -> None:
    key = _seed_widget(web_store)
    headers = {"Origin": "https://shop.example.com"}
    session_body = {"widget_key": key}
    message_body = {
        "session_id": "visitor123456",
        "session_authority": "x" * 32,
        "widget_key": key,
        "content": "Hello",
    }

    cfg = contained_client.get(f"/api/web-chat/config?widget_key={key}", headers=headers)
    assert cfg.status_code == 503
    assert cfg.json()["detail"]["error"] == "WEB_CHAT_UNAVAILABLE"

    session = contained_client.post("/api/web-chat/session", json=session_body, headers=headers)
    assert session.status_code == 503

    msg = contained_client.post("/api/web-chat/session/messages", json=message_body, headers=headers)
    assert msg.status_code == 503

    hb = contained_client.post("/api/web-chat/heartbeat", json={"widget_key": key}, headers=headers)
    assert hb.status_code == 503


def test_containment_blocks_before_session_lookup(contained_client, web_store) -> None:
    key_a = _seed_widget(web_store)
    widget_b = web_store.update_widget(
        "other",
        site_url="https://other.example.com",
        enabled=True,
    )
    web_store.get_or_create_visitor(
        session_id="secret-session-99",
        widget=web_store.get_widget_by_key(key_a),  # type: ignore[arg-type]
        greeting="Hi",
    )

    res = contained_client.post(
        "/api/web-chat/session/messages",
        json={
            "session_id": "secret-session-99",
            "session_authority": "x" * 32,
            "widget_key": widget_b.widget_key,
            "content": "probe",
        },
        headers={"Origin": "https://other.example.com"},
    )
    assert res.status_code == 503
    assert res.json()["detail"]["error"] == "WEB_CHAT_UNAVAILABLE"


def test_cross_tenant_session_id_rejected_when_gate_on(monkeypatch, web_chat_pg_store) -> None:
    monkeypatch.setenv(PUBLIC_AVAILABILITY_ENV, "true")
    from tests.web_chat_acceptance_billing import seed_acceptance_credit_ledger, wire_pg_billing_stores
    from tests.web_chat_acceptance_support import patch_web_chat_store

    store = web_chat_pg_store
    wire_pg_billing_stores(monkeypatch)
    patch_web_chat_store(monkeypatch, store)
    seed_acceptance_credit_ledger(tenant_id="biz", plan_id="max")
    seed_acceptance_credit_ledger(tenant_id="other", plan_id="max")

    key_a = store.update_widget(
        "biz",
        site_url="https://shop.example.com",
        enabled=True,
    ).widget_key
    widget_b = store.update_widget(
        "other",
        site_url="https://other.example.com",
        enabled=True,
    )
    widget_a = store.get_widget_by_key(key_a)
    assert widget_a is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget_a)
    store.get_or_create_visitor(
        session_id="cross-tenant-session",
        widget=widget_a,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    from main import app

    client = TestClient(app)
    res = client.post(
        "/api/web-chat/session/messages",
        json={
            "session_id": "cross-tenant-session",
            "session_authority": bundle.authority_token,
            "widget_key": widget_b.widget_key,
            "content": "probe",
        },
        headers={"Origin": "https://other.example.com"},
    )
    assert res.status_code == 403


def test_web_followup_schedule_noops_when_contained(monkeypatch, sfu_db) -> None:
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    update_settings(
        sfu_db,
        tenant_id="tenant_web",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [{"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"}],
        },
    )
    opened = datetime.now(UTC)
    result = schedule_after_ai_reply(
        sfu_db,
        tenant_id="tenant_web",
        channel=SOURCE_CHANNEL_WEB_CHAT,
        connection_id="wk-web-1",
        conversation_id="web:tenant_web:visitor-1",
        trigger_outbound_intent_id="trigger-web-1",
        control_epoch=1,
        trigger_ai_sent_at=opened,
        channel_context={
            "user_id": "web:visitor-1",
            "social_sender_id": "visitor-1",
            "asset_id": "wk-web-1",
            "meta_binding_id": "wk-web-1",
            "last_inbound_at": opened.isoformat(),
        },
    )
    assert result["scheduled"] is False
    assert result["reason"] == "web_chat_contained"
    assert sfu_db.scalars(select(WhatsAppSmartFollowUpJob)).first() is None


@pytest.mark.asyncio
async def test_web_worker_skips_without_credit_or_delivery(monkeypatch, sfu_db, tmp_path) -> None:
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    from services.credit_ledger_service import CreditLedgerService
    from services.entitlements_service import EntitlementsStore

    ent = EntitlementsStore(root=tmp_path / "sfu-ents")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", ent)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", ent)
    monkeypatch.setattr("services.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: False)
    ledger = CreditLedgerService(root=tmp_path / "sfu-ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    ent.set_plan(tenant_id="tenant_web_worker", plan_id="starter", status="active", source="admin")
    ledger.ensure_period_grant("tenant_web_worker")

    update_settings(
        sfu_db,
        tenant_id="tenant_web_worker",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [{"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"}],
        },
    )
    monkeypatch.setenv(PUBLIC_AVAILABILITY_ENV, "true")
    opened = datetime.now(UTC) - timedelta(minutes=40)
    schedule_after_ai_reply(
        sfu_db,
        tenant_id="tenant_web_worker",
        channel=SOURCE_CHANNEL_WEB_CHAT,
        connection_id="wk-web-worker",
        conversation_id="web:tenant_web_worker:visitor-worker",
        trigger_outbound_intent_id="trigger-web-worker",
        control_epoch=1,
        trigger_ai_sent_at=opened,
        channel_context={
            "user_id": "web:visitor-worker",
            "social_sender_id": "visitor-worker",
            "asset_id": "wk-web-worker",
            "meta_binding_id": "wk-web-worker",
            "last_inbound_at": opened.isoformat(),
        },
    )
    sfu_db.commit()
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)

    job = sfu_db.scalars(select(WhatsAppSmartFollowUpJob)).first()
    assert job is not None
    job.due_at = datetime.now(UTC) - timedelta(minutes=1)
    sfu_db.commit()

    reserve_mock = patch("services.credit_ledger_service.credit_ledger_service.reserve")
    generate_mock = patch(
        "services.smart_followup.worker_job.generate_followup_text",
        new=AsyncMock(return_value="Still need help?"),
    )
    firestore_mock = patch("utils.utils.save_conversation_message_to_firestore", new=AsyncMock())

    with reserve_mock as reserve, generate_mock as generate, firestore_mock as firestore:
        from services.smart_followup.worker import process_due_followup_jobs

        out = await process_due_followup_jobs(limit=5)

    assert out["processed"] == 1
    assert out["results"][0]["status"] == "skipped"
    assert out["results"][0]["reason"] == "web_chat_contained"
    reserve.assert_not_called()
    generate.assert_not_called()
    firestore.assert_not_called()


@pytest.mark.asyncio
async def test_web_adapter_send_skips_when_contained(monkeypatch) -> None:
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    conv = FollowUpConversationView(
        channel=SOURCE_CHANNEL_WEB_CHAT,
        tenant_id="tenant-b",
        conversation_id="web:tenant-b:visitor-2",
        connection_id="wk-b",
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="visitor-2",
    )
    job = WhatsAppSmartFollowUpJob(
        tenant_id="tenant-b",
        channel=SOURCE_CHANNEL_WEB_CHAT,
        connection_id="wk-b",
        conversation_id="web:tenant-b:visitor-2",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=datetime.now(UTC),
        control_epoch=1,
        idempotency_key="idem-contained",
    )
    with patch("utils.utils.save_conversation_message_to_firestore", new=AsyncMock()) as firestore:
        result = await WebFollowUpAdapter().send_followup(
            session=None,  # type: ignore[arg-type]
            job=job,
            conv=conv,
            reply_text="Checking in",
            idempotency_key="idem-contained",
        )
    assert result.status == "skipped"
    assert result.reason == "web_chat_contained"
    firestore.assert_not_called()


def test_meta_schedule_unaffected_when_web_contained(monkeypatch, sfu_db) -> None:
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    repo = WhatsAppCloudRepository(sfu_db)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_meta_ok",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="ph_meta_ok",
        display_phone_number="+96171111001",
        verified_name="Meta OK",
        access_token="token-meta-ok",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["messages"])
    conv = repo.get_or_create_conversation(
        tenant_id="tenant_meta_ok",
        connection_id=conn.id,
        customer_wa_id="96170000003",
        profile_name="Cust",
    )
    conv.last_inbound_at = datetime.now(UTC)
    conv.service_window_opens_at = datetime.now(UTC)
    sfu_db.commit()

    update_settings(
        sfu_db,
        tenant_id="tenant_meta_ok",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [{"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"}],
        },
    )
    result = schedule_after_ai_reply(
        sfu_db,
        tenant_id="tenant_meta_ok",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-meta-ok",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC),
        conversation=conv,
        channel=SOURCE_CHANNEL_WHATSAPP_CLOUD,
    )
    assert result["scheduled"] is True
    job = sfu_db.scalars(select(WhatsAppSmartFollowUpJob)).first()
    assert job is not None
    assert job.channel == SOURCE_CHANNEL_WHATSAPP_CLOUD


@pytest.mark.asyncio
async def test_meta_worker_unaffected_when_web_contained(monkeypatch, sfu_db, tmp_path) -> None:
    monkeypatch.delenv(PUBLIC_AVAILABILITY_ENV, raising=False)
    from services.credit_ledger_service import CreditLedgerService
    from services.entitlements_service import EntitlementsStore

    ent = EntitlementsStore(root=tmp_path / "meta-ents")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", ent)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", ent)
    monkeypatch.setattr("services.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: False)
    ledger = CreditLedgerService(root=tmp_path / "meta-ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)

    def grant(tenant_id: str) -> None:
        ent.set_plan(tenant_id=tenant_id, plan_id="starter", status="active", source="admin")
        ledger.ensure_period_grant(tenant_id)

    grant("tenant_meta_worker")
    update_settings(
        sfu_db,
        tenant_id="tenant_meta_worker",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [{"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"}],
        },
    )
    opened = datetime.now(UTC) - timedelta(minutes=40)
    schedule_after_ai_reply(
        sfu_db,
        tenant_id="tenant_meta_worker",
        channel=SOURCE_CHANNEL_FACEBOOK_MESSENGER,
        connection_id="binding-fb-contain",
        conversation_id="conv-fb-contain",
        trigger_outbound_intent_id="trigger-fb-contain",
        control_epoch=1,
        trigger_ai_sent_at=opened,
        channel_context={
            "user_id": "tenant_meta_worker:facebook:378696005334409:sender-fb",
            "social_sender_id": "sender-fb",
            "asset_id": "378696005334409",
            "meta_binding_id": "binding-fb-contain",
            "last_inbound_at": opened.isoformat(),
        },
    )
    sfu_db.commit()

    job = sfu_db.scalars(select(WhatsAppSmartFollowUpJob)).first()
    job.due_at = datetime.now(UTC) - timedelta(minutes=1)
    sfu_db.commit()

    with (
        patch(
            "services.smart_followup.worker_job.generate_followup_text",
            new=AsyncMock(return_value="Still need help?"),
        ),
        patch(
            "services.channel_capability_state.dm_capability_state",
            return_value={"requested_enabled": True},
        ),
        patch(
            "services.smart_followup.adapters.meta_dm._load_firestore_conversation",
            new=AsyncMock(return_value={"state": {"human_takeover_active": False}, "history": []}),
        ),
        patch(
            "services.requests.delivery.deliver_meta_dm",
            new=AsyncMock(
                return_value=type(
                    "R", (), {"status": "sent", "provider_message_id": "mid-contain", "error_redacted": None}
                )()
            ),
        ),
    ):
        from services.smart_followup.worker import process_due_followup_jobs

        out = await process_due_followup_jobs(limit=5)

    assert out["processed"] == 1
    assert out["results"][0]["status"] == "sent"
    assert out["results"][0]["channel"] == SOURCE_CHANNEL_FACEBOOK_MESSENGER
