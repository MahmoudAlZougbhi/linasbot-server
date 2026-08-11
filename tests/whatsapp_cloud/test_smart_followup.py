"""Smart Follow-Up — settings, window, concurrency, credits, cancellation."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

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
os.environ["WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_AI_REPLIES_ENABLED"] = "true"
os.environ["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] = "false"
os.environ["PUBLIC_URL"] = "https://example.test"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402
from services.whatsapp_cloud.smart_followup.eligibility import (  # noqa: E402
    evaluate_job_eligibility,
    window_allows_send,
)
from services.whatsapp_cloud.smart_followup.hooks import (  # noqa: E402
    cancel_conversation_followups,
    schedule_after_ai_reply,
)
from services.whatsapp_cloud.smart_followup.opt_out import looks_like_opt_out  # noqa: E402
from services.whatsapp_cloud.smart_followup.repository import SmartFollowUpRepository  # noqa: E402
from services.whatsapp_cloud.smart_followup.settings_service import (  # noqa: E402
    SmartFollowUpSettingsError,
    get_or_create_settings,
    update_settings,
)


@pytest.fixture()
def wa_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'wa_sfu.db'}"
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


def _seed_connected(session, *, tenant_id: str = "tenant_sfu") -> tuple[Any, Any]:
    repo = WhatsAppCloudRepository(session)
    conn = repo.create_connection_with_credential(
        tenant_id=tenant_id,
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="ph_sfu_1",
        display_phone_number="+96171111000",
        verified_name="SFU",
        access_token="token-sfu",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    repo.mark_connection_connected(conn, webhook_fields=["messages"])
    conn.ai_default_enabled = True
    repo.grant_pilot(tenant_id=tenant_id, granted_by_user_id="owner", reason="test_pilot")
    conv = repo.get_or_create_conversation(
        tenant_id=tenant_id,
        connection_id=conn.id,
        customer_wa_id="96170000001",
        profile_name="Cust",
    )
    conv.last_inbound_at = datetime.now(UTC)
    conv.service_window_opens_at = datetime.now(UTC)
    session.commit()
    return conn, conv


def test_settings_defaults_and_validation(wa_db):
    view = get_or_create_settings(wa_db, "tenant_sfu")
    assert view["enabled"] is False
    assert view["business_hours_only"] is True
    assert view["billing_mode"] == "customer_direct"
    assert len(view["steps"]) == 3
    assert view["steps"][0]["delay_minutes"] == 30
    assert view["steps"][1]["delay_minutes"] == 360
    assert view["steps"][2]["delay_minutes"] == 1200

    with pytest.raises(SmartFollowUpSettingsError):
        update_settings(
            wa_db,
            tenant_id="tenant_sfu",
            actor_user_id="u1",
            payload={
                "steps": [
                    {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
                    {"step_index": 2, "enabled": True, "delay_minutes": 20, "goal": "offer_more_help"},
                ]
            },
        )

    with pytest.raises(SmartFollowUpSettingsError):
        update_settings(
            wa_db,
            tenant_id="tenant_sfu",
            actor_user_id="u1",
            payload={"billing_mode": "solution_partner"},
        )

    updated = update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "steps": [
                {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
            ],
        },
        expected_version=view["settings_version"],
    )
    assert updated["enabled"] is True
    assert len(updated["steps"]) == 1

    with pytest.raises(SmartFollowUpSettingsError) as exc:
        update_settings(
            wa_db,
            tenant_id="tenant_sfu",
            actor_user_id="u1",
            payload={"enabled": False},
            expected_version=view["settings_version"],
        )
    assert exc.value.code == "version_conflict"


def test_absolute_delays_not_cumulative(wa_db):
    conn, conv = _seed_connected(wa_db)
    update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [
                {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
                {"step_index": 2, "enabled": True, "delay_minutes": 360, "goal": "offer_more_help"},
                {"step_index": 3, "enabled": True, "delay_minutes": 1200, "goal": "politely_close"},
            ],
        },
    )
    sent_at = datetime(2026, 8, 11, 12, 0, 0, tzinfo=UTC)
    result = schedule_after_ai_reply(
        wa_db,
        tenant_id="tenant_sfu",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-1",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=sent_at,
        conversation=conv,
    )
    assert result["scheduled"] is True
    jobs = list(
        wa_db.scalars(
            __import__("sqlalchemy")
            .select(
                __import__(
                    "db.models.whatsapp_smart_followup", fromlist=["WhatsAppSmartFollowUpJob"]
                ).WhatsAppSmartFollowUpJob
            )
            .where(
                __import__(
                    "db.models.whatsapp_smart_followup", fromlist=["WhatsAppSmartFollowUpJob"]
                ).WhatsAppSmartFollowUpJob.sequence_id
                == result["sequence_id"]
            )
        ).all()
    )
    assert len(jobs) == 3
    by_step = {j.step_index: j for j in jobs}

    def _naive(dt: datetime) -> datetime:
        return dt.replace(tzinfo=None) if dt.tzinfo else dt

    assert _naive(by_step[1].due_at) == _naive(sent_at + timedelta(minutes=30))
    assert _naive(by_step[2].due_at) == _naive(sent_at + timedelta(minutes=360))
    assert _naive(by_step[3].due_at) == _naive(sent_at + timedelta(minutes=1200))
    # Prove non-cumulative: step2 is NOT step1+6h from step1 due.
    assert _naive(by_step[2].due_at) != _naive(by_step[1].due_at + timedelta(minutes=360))


def test_window_23h_ok_buffer_and_exact_expiry(wa_db):
    _conn, conv = _seed_connected(wa_db)
    opened = datetime(2026, 8, 11, 0, 0, 0, tzinfo=UTC)
    conv.service_window_opens_at = opened
    conv.last_inbound_at = opened

    ok, reason = window_allows_send(conv=conv, now=opened + timedelta(hours=23))
    assert ok is True
    assert reason is None

    # Inside safety buffer (12 min) — reject.
    ok, reason = window_allows_send(conv=conv, now=opened + timedelta(hours=24) - timedelta(minutes=5))
    assert ok is False
    assert reason == "safety_buffer_insufficient"

    # Exact/after 24h — reject.
    ok, reason = window_allows_send(conv=conv, now=opened + timedelta(hours=24))
    assert ok is False
    assert reason == "customer_service_window_expired"

    ok, reason = window_allows_send(conv=conv, now=opened + timedelta(hours=24, minutes=1))
    assert ok is False


def test_customer_reply_cancels_queued(wa_db):
    conn, conv = _seed_connected(wa_db)
    update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [
                {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
            ],
        },
    )
    schedule_after_ai_reply(
        wa_db,
        tenant_id="tenant_sfu",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-2",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC),
        conversation=conv,
    )
    cancelled = cancel_conversation_followups(
        wa_db,
        tenant_id="tenant_sfu",
        conversation_id=conv.id,
        reason="customer_reply",
    )
    assert cancelled >= 1
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    jobs = list(wa_db.scalars(__import__("sqlalchemy").select(WhatsAppSmartFollowUpJob)).all())
    assert all(j.status == "cancelled" for j in jobs)


def test_feature_disabled_invalidates_queue(wa_db):
    conn, conv = _seed_connected(wa_db)
    view = update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [
                {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
            ],
        },
    )
    schedule_after_ai_reply(
        wa_db,
        tenant_id="tenant_sfu",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-3",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC),
        conversation=conv,
    )
    update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={"enabled": False},
        expected_version=view["settings_version"],
    )
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    jobs = list(wa_db.scalars(__import__("sqlalchemy").select(WhatsAppSmartFollowUpJob)).all())
    assert jobs
    assert all(j.status == "cancelled" for j in jobs)


def test_duplicate_worker_claim(wa_db):
    conn, conv = _seed_connected(wa_db)
    update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [
                {"step_index": 1, "enabled": True, "delay_minutes": 1, "goal": "gentle_check_in"},
            ],
        },
    )
    # Schedule due in the past.
    result = schedule_after_ai_reply(
        wa_db,
        tenant_id="tenant_sfu",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-4",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC) - timedelta(minutes=5),
        conversation=conv,
    )
    assert result["scheduled"] is True
    wa_db.commit()

    sfu_a = SmartFollowUpRepository(wa_db)
    claimed_a = sfu_a.claim_due_jobs(worker_id="worker-a", limit=10)
    claimed_b = sfu_a.claim_due_jobs(worker_id="worker-b", limit=10)
    assert len(claimed_a) == 1
    assert claimed_b == []


def test_opt_out_phrases():
    assert looks_like_opt_out("STOP")
    assert looks_like_opt_out("توقف")
    assert looks_like_opt_out("unsubscribe please")
    assert not looks_like_opt_out("please continue helping me")
    assert not looks_like_opt_out("")


def test_history_and_status_do_not_schedule(wa_db):
    """History sync / status events must never create follow-up jobs (covered via no schedule call)."""
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    _seed_connected(wa_db)
    jobs = list(wa_db.scalars(__import__("sqlalchemy").select(WhatsAppSmartFollowUpJob)).all())
    assert jobs == []


def test_tenant_isolation_settings(wa_db):
    get_or_create_settings(wa_db, "tenant_a")
    update_settings(
        wa_db,
        tenant_id="tenant_a",
        actor_user_id="u1",
        payload={"enabled": True},
    )
    view_b = get_or_create_settings(wa_db, "tenant_b")
    assert view_b["enabled"] is False


def test_no_monty_fallback_in_smart_followup_package():
    root = os.path.join(os.path.dirname(__file__), "..", "..", "services", "whatsapp_cloud", "smart_followup")
    for name in os.listdir(root):
        if not name.endswith(".py"):
            continue
        text = open(os.path.join(root, name), encoding="utf-8").read().lower()
        assert "montymobile" not in text
        assert "monty_mobile" not in text
        assert "smart_messaging" not in text


def test_eligibility_epoch_and_pause(wa_db):
    conn, conv = _seed_connected(wa_db)
    update_settings(
        wa_db,
        tenant_id="tenant_sfu",
        actor_user_id="u1",
        payload={
            "enabled": True,
            "business_hours_only": False,
            "steps": [
                {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
            ],
        },
    )
    schedule_after_ai_reply(
        wa_db,
        tenant_id="tenant_sfu",
        connection_id=conn.id,
        conversation_id=conv.id,
        trigger_outbound_intent_id="intent-5",
        control_epoch=int(conv.control_epoch),
        trigger_ai_sent_at=datetime.now(UTC) - timedelta(minutes=40),
        conversation=conv,
    )
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob

    job = wa_db.scalars(__import__("sqlalchemy").select(WhatsAppSmartFollowUpJob)).first()
    assert job is not None
    settings = SmartFollowUpRepository(wa_db).get_settings("tenant_sfu")

    with (
        patch(
            "services.whatsapp_cloud.smart_followup.eligibility.evaluate_ai_eligibility",
            return_value=(True, None),
        ),
        patch(
            "services.whatsapp_cloud.smart_followup.eligibility._tenant_suspend_reason",
            return_value=None,
        ),
    ):
        ok, reason = evaluate_job_eligibility(wa_db, job=job, settings=settings, conn=conn, conv=conv)
        assert ok is True

        conv.control_state = "HUMAN_PAUSED"
        ok, reason = evaluate_job_eligibility(wa_db, job=job, settings=settings, conn=conn, conv=conv)
        assert ok is False
        assert reason == "conversation_paused"

        conv.control_state = "AI_ACTIVE"
        conv.control_epoch = int(job.control_epoch) + 1
        ok, reason = evaluate_job_eligibility(wa_db, job=job, settings=settings, conn=conn, conv=conv)
        assert ok is False
        assert reason == "epoch_changed"
