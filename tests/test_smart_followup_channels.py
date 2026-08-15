"""Smart Follow-Up channel routing tests."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ["META_CREDENTIAL_ENCRYPTION_KEY"] = "x" * 32

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.constants import (  # noqa: E402
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)
from services.smart_followup.channels import get_channel_adapter, normalize_followup_channel  # noqa: E402
from services.smart_followup.hooks import schedule_after_ai_reply  # noqa: E402
from services.smart_followup.settings_service import update_settings  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402


@pytest.fixture()
def sfu_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'sfu_channels.db'}"
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


@pytest.fixture()
def sfu_credit_entitlement(tmp_path, monkeypatch):
    """Provision active credits for SFU worker routing tests."""
    from services.credit_ledger_service import CreditLedgerService
    from services.entitlements_service import EntitlementsStore

    store = EntitlementsStore(root=tmp_path / "sfu-ents")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_pg_ops.entitlements_store", store)
    ledger = CreditLedgerService(root=tmp_path / "sfu-ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    monkeypatch.setattr(
        "services.credit_ai_gate.ai_generation_blocked",
        lambda *_a, **_k: False,
    )

    def grant(tenant_id: str) -> None:
        store.set_plan(tenant_id=tenant_id, plan_id="starter", status="active", source="admin")
        ledger.ensure_period_grant(tenant_id)

    return grant


def test_normalize_followup_channel():
    assert normalize_followup_channel("whatsapp") == SOURCE_CHANNEL_WHATSAPP_CLOUD
    assert normalize_followup_channel("instagram") == SOURCE_CHANNEL_INSTAGRAM_DM
    assert normalize_followup_channel("facebook_messenger") == SOURCE_CHANNEL_FACEBOOK_MESSENGER
    with pytest.raises(ValueError):
        normalize_followup_channel("sms")


def test_get_channel_adapter_routing():
    assert get_channel_adapter(SOURCE_CHANNEL_WHATSAPP_CLOUD).channel == SOURCE_CHANNEL_WHATSAPP_CLOUD
    assert get_channel_adapter("instagram").channel == SOURCE_CHANNEL_INSTAGRAM_DM
    assert get_channel_adapter("facebook").channel == SOURCE_CHANNEL_FACEBOOK_MESSENGER


def test_schedule_whatsapp_stores_default_channel(sfu_db):
    repo = WhatsAppCloudRepository(sfu_db)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_route",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="ph_route_1",
        display_phone_number="+96171111000",
        verified_name="Route",
        access_token="token-route",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["messages"])
    conv = repo.get_or_create_conversation(
        tenant_id="tenant_route",
        connection_id=conn.id,
        customer_wa_id="96170000002",
        profile_name="Cust",
    )
    conv.last_inbound_at = datetime.now(UTC)
    conv.service_window_opens_at = datetime.now(UTC)
    sfu_db.commit()

    update_settings(
        sfu_db,
        tenant_id="tenant_route",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [{"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"}],
        },
    )
    result = schedule_after_ai_reply(
        sfu_db,
        tenant_id="tenant_route",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-wa-1",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC),
        conversation=conv,
        channel=SOURCE_CHANNEL_WHATSAPP_CLOUD,
    )
    assert result["scheduled"] is True
    job = sfu_db.scalars(
        __import__("sqlalchemy").select(
            __import__(
                "db.models.whatsapp_smart_followup", fromlist=["WhatsAppSmartFollowUpJob"]
            ).WhatsAppSmartFollowUpJob
        )
    ).first()
    assert job.channel == SOURCE_CHANNEL_WHATSAPP_CLOUD


def test_schedule_meta_stores_channel_context(sfu_db):
    update_settings(
        sfu_db,
        tenant_id="tenant_meta",
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
        tenant_id="tenant_meta",
        channel=SOURCE_CHANNEL_INSTAGRAM_DM,
        connection_id="binding-ig-1",
        conversation_id="conv-ig-1",
        trigger_outbound_intent_id="trigger-ig-1",
        control_epoch=1,
        trigger_ai_sent_at=opened,
        channel_context={
            "user_id": "tenant_meta:instagram:17841413184256533:sender-1",
            "social_sender_id": "sender-1",
            "asset_id": "17841413184256533",
            "meta_binding_id": "binding-ig-1",
            "last_inbound_at": opened.isoformat(),
            "profile_name": "Ada",
        },
    )
    assert result["scheduled"] is True
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    job = sfu_db.scalars(__import__("sqlalchemy").select(WhatsAppSmartFollowUpJob)).first()
    assert job.channel == SOURCE_CHANNEL_INSTAGRAM_DM
    assert job.channel_context["social_sender_id"] == "sender-1"


@pytest.mark.asyncio
async def test_meta_worker_routes_to_deliver_meta_dm(sfu_db, sfu_credit_entitlement):
    sfu_credit_entitlement("tenant_meta_send")
    update_settings(
        sfu_db,
        tenant_id="tenant_meta_send",
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
        tenant_id="tenant_meta_send",
        channel=SOURCE_CHANNEL_FACEBOOK_MESSENGER,
        connection_id="binding-fb-1",
        conversation_id="conv-fb-1",
        trigger_outbound_intent_id="trigger-fb-1",
        control_epoch=1,
        trigger_ai_sent_at=opened,
        channel_context={
            "user_id": "tenant_meta_send:facebook:378696005334409:sender-fb",
            "social_sender_id": "sender-fb",
            "asset_id": "378696005334409",
            "meta_binding_id": "binding-fb-1",
            "last_inbound_at": opened.isoformat(),
        },
    )
    sfu_db.commit()

    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    job = sfu_db.scalars(__import__("sqlalchemy").select(WhatsAppSmartFollowUpJob)).first()
    job.due_at = datetime.now(UTC) - timedelta(minutes=1)
    sfu_db.commit()

    with (
        patch(
            "services.smart_followup.worker_job.generate_followup_text",
            new=AsyncMock(return_value="Still need help?"),
        ),
        patch(
            "services.channel_capability_state.dm_capability_state",
            return_value={"effective_enabled": True},
        ),
        patch(
            "services.smart_followup.adapters.meta_dm._load_firestore_conversation",
            new=AsyncMock(return_value={"state": {"human_takeover_active": False}, "history": []}),
        ),
        patch(
            "services.requests.delivery.deliver_meta_dm",
            new=AsyncMock(
                return_value=type("R", (), {"status": "sent", "provider_message_id": "mid-1", "error_redacted": None})()
            ),
        ),
    ):
        from services.smart_followup.worker import process_due_followup_jobs

        out = await process_due_followup_jobs(limit=5)
        assert out["processed"] == 1
        assert out["results"][0]["status"] == "sent"
        assert out["results"][0]["channel"] == SOURCE_CHANNEL_FACEBOOK_MESSENGER


def test_schedule_skips_disabled_channel(sfu_db):
    update_settings(
        sfu_db,
        tenant_id="tenant_off",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "channels_enabled": {
                "whatsapp_cloud": False,
                "instagram_dm": True,
                "facebook_messenger": True,
            },
            "steps": [{"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"}],
        },
    )
    repo = WhatsAppCloudRepository(sfu_db)
    conn = repo.create_connection_with_credential(
        tenant_id="tenant_off",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="waba-off",
        phone_number_id="pn-off",
        display_phone_number="+96170000002",
        verified_name="Off",
        access_token="token-off",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    conv = repo.get_or_create_conversation(
        tenant_id="tenant_off",
        connection_id=conn.id,
        customer_wa_id="96171111111",
    )
    result = schedule_after_ai_reply(
        sfu_db,
        tenant_id="tenant_off",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-off",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC),
        conversation=conv,
        channel=SOURCE_CHANNEL_WHATSAPP_CLOUD,
    )
    assert result["scheduled"] is False
    assert result["reason"] == "channel_disabled"
