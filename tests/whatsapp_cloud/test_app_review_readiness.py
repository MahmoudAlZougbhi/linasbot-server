"""Redacted App Review readiness, bind dry-run, webhook HTTP, outbound retry."""

from __future__ import annotations

import hashlib
import hmac
import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
    monkeypatch.setenv("META_WHATSAPP_APP_REVIEW_ALLOWED_WABA_IDS", TEST_WABA)
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
    full_number = "+1 555 010 9876"
    repo = WhatsAppCloudRepository(wa_db)
    repo.create_connection_with_credential(
        tenant_id="linas",
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id=TEST_WABA,
        phone_number_id=TEST_PHONE,
        display_phone_number=full_number,
        verified_name="Linas Test",
        access_token="tenant-token-not-for-readiness",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    wa_db.commit()

    payload = build_app_review_readiness(tenant_id="linas")
    assert payload["success"] is True
    assert payload["public_availability"] is False
    assert payload["flags"]["public_availability"] is False
    assert payload["coexistence_feature"] == "whatsapp_business_app_onboarding"
    blob = str(payload)
    assert TEST_TOKEN not in blob
    assert "EAAG" not in blob
    assert full_number not in blob
    assert "display_phone_number" not in blob
    assert payload["connections"][0]["display_phone_last4"] == "9876"
    assert payload["config_keys_present"]["WHATSAPP_CLOUD_PUBLIC_AVAILABILITY"] is True
    fp1 = whatsapp_rollout_fingerprint()
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "true")
    fp2 = whatsapp_rollout_fingerprint()
    assert fp1 != fp2
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    assert whatsapp_rollout_fingerprint() == fp1


def test_redaction_masks_tokens_and_long_numbers() -> None:
    text = redact_whatsapp_text("token=not-a-live-token dest=155501001234")
    assert "155501001234" not in text
    assert "1234" in text
    live_like = redact_whatsapp_text("token=" + ("EAA" + ("Z" * 40)))
    assert "EAA" + ("Z" * 40) not in live_like
    assert "[redacted-token]" in live_like


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
        from services.meta_app_registry import APP_A_KEY, get_meta_app_configs

        app_a = get_meta_app_configs()[APP_A_KEY]
        secret = (app_a.app_secret if app_a is not None else "").encode()
        if secret:
            sig = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
            accepted = client.post("/webhook/whatsapp-cloud", content=body, headers={"X-Hub-Signature-256": sig})
            assert accepted.status_code == 200
        bridge = client.get("/integrations/whatsapp/embedded-signup?state=x&config_id=cfg")
        assert bridge.status_code == 200
        assert "whatsapp_business_app_onboarding" in bridge.text
        assert "Connect a WhatsApp Business app" in bridge.text
        assert "Add a new number" in bridge.text
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
        control_epoch=int(conv.control_epoch),
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("control_state", "epoch_delta", "error_detail"),
    [
        ("HUMAN_PAUSED", 0, "conversation_not_ai_active"),
        ("AI_ACTIVE", 1, "control_epoch_changed"),
    ],
)
async def test_outbound_delivery_suppresses_stale_control_before_provider_send(
    wa_db,
    monkeypatch,
    control_state,
    epoch_delta,
    error_detail,
):
    from services.whatsapp_cloud import delivery_retry as dr

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
    conv = repo.get_or_create_conversation(
        tenant_id="linas",
        connection_id=conn.id,
        customer_wa_id="15551230000",
    )
    created_epoch = int(conv.control_epoch)
    intent, created = repo.create_outbound_intent(
        tenant_id="linas",
        connection_id=conn.id,
        conversation_id=conv.id,
        idempotency_key=f"stale-{control_state}-{epoch_delta}",
        control_epoch=created_epoch,
        triggering_inbound_message_id=None,
    )
    assert created is True
    assert intent is not None
    intent.canonical_text = "must not send"
    conv.control_state = control_state
    conv.control_epoch = created_epoch + epoch_delta
    wa_db.commit()

    @contextmanager
    def _sess(*, require: bool = True):
        yield wa_db
        wa_db.commit()

    monkeypatch.setattr(dr, "whatsapp_session", _sess)
    sends = {"n": 0}

    async def _send(**kwargs: Any) -> dict[str, Any]:
        sends["n"] += 1
        return {"messages": [{"id": "wamid.must-not-exist"}]}

    monkeypatch.setattr(dr, "send_text_message", _send)

    result = await dr.send_canonical_intent(intent.id)

    assert result == {"ok": True, "skipped": True, "reason": "stale_control_state"}
    assert sends["n"] == 0
    assert intent.dispatch_state == "suppressed"
    assert intent.control_epoch_at_send == int(conv.control_epoch)
    assert intent.error_code == "epoch_race"
    assert intent.error_detail == error_detail
    from db.models.whatsapp_cloud import WhatsAppMessage

    assert list(wa_db.scalars(select(WhatsAppMessage)).all()) == []


@pytest.mark.asyncio
async def test_outbound_delivery_finalizes_ai_reply_once(wa_db, monkeypatch):
    from db.models.whatsapp_cloud import WhatsAppMessage, WhatsAppOutboundIntent
    from services.whatsapp_cloud import delivery_retry as dr
    from services.whatsapp_cloud import outbound_finalization as finalization
    from services.whatsapp_cloud.smart_followup import hooks as followup_hooks

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
    conv = repo.get_or_create_conversation(
        tenant_id="linas",
        connection_id=conn.id,
        customer_wa_id="15551230000",
    )
    inbound, inbound_created = repo.insert_message(
        tenant_id="linas",
        connection_id=conn.id,
        conversation_id=conv.id,
        provider_message_id="wamid.customer",
        origin="CUSTOMER",
        direction="inbound",
        message_type="text",
        content_preview="question",
    )
    assert inbound_created is True
    assert inbound is not None
    intent, created = repo.create_outbound_intent(
        tenant_id="linas",
        connection_id=conn.id,
        conversation_id=conv.id,
        idempotency_key="finalize-once",
        control_epoch=int(conv.control_epoch),
        triggering_inbound_message_id=inbound.id,
    )
    assert created is True
    assert intent is not None
    intent.canonical_text = "clinic answer"
    wa_db.commit()

    @contextmanager
    def _sess(*, require: bool = True):
        yield wa_db
        wa_db.commit()

    monkeypatch.setattr(dr, "whatsapp_session", _sess)
    provider_sends = {"n": 0}
    analytics_calls: list[dict[str, Any]] = []
    event_calls: list[tuple[str, dict[str, Any]]] = []
    followup_calls: list[dict[str, Any]] = []

    async def _send(**kwargs: Any) -> dict[str, Any]:
        provider_sends["n"] += 1
        return {"messages": [{"id": "wamid.ai"}]}

    monkeypatch.setattr(dr, "send_text_message", _send)
    monkeypatch.setattr(finalization, "record_analytics_channel_usage", lambda **kwargs: analytics_calls.append(kwargs))
    monkeypatch.setattr(finalization, "emit_wa_event", lambda event, **kwargs: event_calls.append((event, kwargs)))
    monkeypatch.setattr(
        followup_hooks,
        "schedule_after_ai_reply",
        lambda _session, **kwargs: followup_calls.append(kwargs) or {"scheduled": True},
    )

    first = await dr.send_canonical_intent(intent.id)
    second = await dr.send_canonical_intent(intent.id)

    assert first == {"ok": True, "wamid": "wamid.ai", "finalized": True}
    assert second["ok"] is True
    assert second["skipped"] is True
    assert second["reason"] == "already_sent"
    assert provider_sends["n"] == 1
    persisted_intent = wa_db.get(WhatsAppOutboundIntent, intent.id)
    assert persisted_intent is not None
    assert persisted_intent.dispatch_state == "sent"
    assert persisted_intent.provider_wamid == "wamid.ai"
    outbound = list(
        wa_db.scalars(
            select(WhatsAppMessage).where(
                WhatsAppMessage.direction == "outbound",
                WhatsAppMessage.provider_message_id == "wamid.ai",
            )
        ).all()
    )
    assert len(outbound) == 1
    assert outbound[0].content_preview == "clinic answer"
    assert outbound[0].meta == {"source": "AI"}
    assert conv.last_ai_outbound_at is not None
    assert analytics_calls == [
        {
            "tenant_id": "linas",
            "connection_id": conn.id,
            "conversation_id": conv.id,
            "provider_message_id": "wamid.customer",
            "source": "ai_reply",
        }
    ]
    assert [event for event, _fields in event_calls] == ["ai_reply_sent"]
    assert len(followup_calls) == 1
    assert followup_calls[0]["trigger_outbound_intent_id"] == intent.id


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_point", ["finalizer", "context_commit"])
async def test_post_provider_success_finalization_failure_requires_reconciliation_without_resend(
    wa_db,
    monkeypatch,
    failure_point,
):
    from db.models.whatsapp_cloud import WhatsAppMessage, WhatsAppOutboundIntent
    from services.whatsapp_cloud import delivery_retry as dr

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
    conv = repo.get_or_create_conversation(
        tenant_id="linas",
        connection_id=conn.id,
        customer_wa_id="15551230000",
    )
    intent, created = repo.create_outbound_intent(
        tenant_id="linas",
        connection_id=conn.id,
        conversation_id=conv.id,
        idempotency_key=f"post-send-failure-{failure_point}",
        control_epoch=int(conv.control_epoch),
        triggering_inbound_message_id=None,
    )
    assert created is True
    assert intent is not None
    intent.canonical_text = "provider accepted this"
    wa_db.commit()
    intent_id = intent.id

    contexts = {"n": 0}

    @contextmanager
    def _sess(*, require: bool = True):
        contexts["n"] += 1
        context_number = contexts["n"]
        try:
            yield wa_db
            if failure_point == "context_commit" and context_number == 2:
                wa_db.rollback()
                raise RuntimeError("injected_finalization_commit_failure")
            wa_db.commit()
        except Exception:
            wa_db.rollback()
            raise

    monkeypatch.setattr(dr, "whatsapp_session", _sess)
    provider_sends = {"n": 0}

    async def _send(**kwargs: Any) -> dict[str, Any]:
        provider_sends["n"] += 1
        return {"messages": [{"id": "wamid.provider-accepted"}]}

    monkeypatch.setattr(dr, "send_text_message", _send)
    if failure_point == "finalizer":
        monkeypatch.setattr(
            dr,
            "finalize_ai_outbound_sent",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("injected_finalizer_failure")),
        )

    first = await dr.send_canonical_intent(intent_id)
    second = await dr.send_canonical_intent(intent_id)

    assert first == {
        "ok": False,
        "retryable": False,
        "reason": "post_send_finalization_failed",
        "reconciliation_required": True,
        "wamid": "wamid.provider-accepted",
    }
    assert second == {"ok": True, "skipped": True, "reason": "already_reconciliation_required"}
    assert provider_sends["n"] == 1
    persisted = wa_db.get(WhatsAppOutboundIntent, intent_id)
    assert persisted is not None
    assert persisted.dispatch_state == "reconciliation_required"
    assert persisted.provider_wamid == "wamid.provider-accepted"
    assert persisted.error_code == "post_send_finalization_failed"
    assert persisted.error_detail.startswith("provider_send_succeeded:")
    assert persisted.attempt_count == 1
    outbound = list(
        wa_db.scalars(
            select(WhatsAppMessage).where(
                WhatsAppMessage.direction == "outbound",
                WhatsAppMessage.provider_message_id == "wamid.provider-accepted",
            )
        ).all()
    )
    assert outbound == []


@pytest.mark.asyncio
async def test_minute_retry_job_reconciles_only_stale_sending_without_provider_resend(wa_db, monkeypatch):
    from db.models.whatsapp_cloud import WhatsAppOutboundIntent
    from services.whatsapp_cloud import delivery_retry as dr

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
    conv = repo.get_or_create_conversation(
        tenant_id="linas",
        connection_id=conn.id,
        customer_wa_id="15551230000",
    )

    def _intent(key: str) -> WhatsAppOutboundIntent:
        row, created = repo.create_outbound_intent(
            tenant_id="linas",
            connection_id=conn.id,
            conversation_id=conv.id,
            idempotency_key=key,
            control_epoch=int(conv.control_epoch),
            triggering_inbound_message_id=None,
        )
        assert created is True
        assert row is not None
        row.canonical_text = key
        row.dispatch_state = "sending"
        row.attempt_count = 1
        return row

    stale_unknown = _intent("stale-sending-unknown")
    stale_known = _intent("stale-sending-known")
    stale_known.provider_wamid = "wamid.already-accepted"
    fresh = _intent("fresh-sending")
    now = datetime.now(UTC)
    stale_at = now - dr.SENDING_RECONCILIATION_TIMEOUT - timedelta(seconds=1)
    stale_unknown.updated_at = stale_at
    stale_known.updated_at = stale_at
    fresh.updated_at = now
    wa_db.commit()
    ids = (stale_unknown.id, stale_known.id, fresh.id)

    @contextmanager
    def _sess(*, require: bool = True):
        try:
            yield wa_db
            wa_db.commit()
        except Exception:
            wa_db.rollback()
            raise

    monkeypatch.setattr(dr, "whatsapp_session", _sess)
    provider_sends = {"n": 0}

    async def _send(**kwargs: Any) -> dict[str, Any]:
        provider_sends["n"] += 1
        raise AssertionError("stale sending reconciliation must never call provider")

    monkeypatch.setattr(dr, "send_text_message", _send)

    result = await dr.retry_pending_outbound_intents(tenant_id="linas")

    assert result["ok"] is True
    assert result["attempted"] == 0
    assert result["stale_sending_reconciled"] == 2
    assert provider_sends["n"] == 0
    wa_db.expire_all()
    persisted_unknown = wa_db.get(WhatsAppOutboundIntent, ids[0])
    persisted_known = wa_db.get(WhatsAppOutboundIntent, ids[1])
    persisted_fresh = wa_db.get(WhatsAppOutboundIntent, ids[2])
    assert persisted_unknown is not None
    assert persisted_known is not None
    assert persisted_fresh is not None
    assert persisted_unknown.dispatch_state == "reconciliation_required"
    assert persisted_unknown.error_code == "stale_sending_unknown_outcome"
    assert persisted_unknown.provider_wamid is None
    assert persisted_known.dispatch_state == "reconciliation_required"
    assert persisted_known.error_code == "stale_sending_with_wamid"
    assert persisted_known.provider_wamid == "wamid.already-accepted"
    assert persisted_fresh.dispatch_state == "sending"
    assert persisted_fresh.error_code is None

    # A later minute tick keeps reconciliation rows off the retry path.
    again = await dr.retry_pending_outbound_intents(tenant_id="linas")
    assert again["attempted"] == 0
    assert again["stale_sending_reconciled"] == 0
    assert provider_sends["n"] == 0
