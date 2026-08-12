"""AI request capture tool + wa.me gate tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.ai_tool import AiToolContext, execute_create_customer_request  # noqa: E402
from services.requests.capture import (  # noqa: E402
    appointment_pending_confirmation_message,
    skip_forced_booking_wa_me,
)
from services.requests.intent import is_appointment_or_order_intent, is_order_intent  # noqa: E402


@pytest.fixture()
def req_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'requests_ai.db'}"
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


def test_appointment_pending_wording():
    text = appointment_pending_confirmation_message("en")
    assert "pending" in text.lower() or "confirm" in text.lower()


def test_intent_helpers():
    assert is_appointment_or_order_intent("I want to book an appointment tomorrow")
    assert is_order_intent("I want to order the serum")


def test_ai_tool_refuses_when_setup_inactive(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _t: False)
    ctx = AiToolContext(
        tenant_id="t1",
        source_channel="instagram_dm",
        conversation_id="c1",
        external_customer_id="u1",
    )
    out = execute_create_customer_request(
        {
            "request_type": "APPOINTMENT",
            "customer_confirmed": True,
            "idempotency_key": "idem-ai-001",
            "title": "Consult",
        },
        ctx,
        session=req_db,
    )
    assert out.get("ok") is False
    assert out.get("error") == "REQUESTS_SETUP_REQUIRED"


def test_ai_tool_create_after_confirm(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _t: True)
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _t: True)
    monkeypatch.setattr(
        "services.requests.service.published_configuration_version",
        lambda _t: "v1",
    )
    monkeypatch.setattr(
        "services.requests.ai_tool.published_configuration_version",
        lambda _t: "v1",
    )
    monkeypatch.setattr(
        "services.requests.ai_tool.load_published_requests_config",
        lambda _t: {"module_enabled": True, "enabled_types": ["APPOINTMENT"], "fields": []},
    )
    ctx = AiToolContext(
        tenant_id="t1",
        source_channel="whatsapp_cloud",
        conversation_id="c1",
        external_customer_id="u1",
    )
    args = {
        "request_type": "APPOINTMENT",
        "customer_confirmed": True,
        "idempotency_key": "idem-ai-002",
        "title": "Preferred Friday",
        "preferred_date": "2026-08-20",
        "preferred_time": "afternoon",
    }
    first = execute_create_customer_request(args, ctx, session=req_db)
    assert first.get("ok") is True, first
    second = execute_create_customer_request(args, ctx, session=req_db)
    assert second.get("ok") is True
    assert second.get("request", {}).get("request_id") == first.get("request", {}).get("request_id")


def test_skip_forced_wa_me_when_capture_active(monkeypatch):
    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _t: True)
    assert skip_forced_booking_wa_me("tenant-x") is True
    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _t: False)
    assert skip_forced_booking_wa_me("tenant-x") is False
