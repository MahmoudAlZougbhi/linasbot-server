"""Phase 4: Requests AI capture tool + no forced wa.me when capture active."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.ai_tool import (  # noqa: E402
    CREATE_CUSTOMER_REQUEST_TOOL_NAME,
    AiToolContext,
    appointment_pending_wording,
    execute_create_customer_request,
    tools_for_tenant,
)
from services.requests.capture import (  # noqa: E402
    appointment_pending_confirmation_message,
    public_comment_dm_invite,
    skip_forced_booking_wa_me,
)
from services.requests.intent import (  # noqa: E402
    looks_like_appointment_intent,
    looks_like_order_intent,
)


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


def _ctx(**overrides) -> AiToolContext:
    base = dict(
        tenant_id="tenant-a",
        source_channel="instagram_dm",
        conversation_id="conv-1",
        response_language="en",
        public_comment=False,
    )
    base.update(overrides)
    return AiToolContext(**base)


def test_tools_for_tenant_empty_when_inactive(monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: False)
    assert tools_for_tenant("tenant-a") == []


def test_tools_for_tenant_exposes_create_when_active(monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: True)
    tools = tools_for_tenant("tenant-a")
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == CREATE_CUSTOMER_REQUEST_TOOL_NAME


def test_appointment_pending_wording_helper():
    en = appointment_pending_wording("en")
    assert "pending" in en.lower()
    assert "confirm" in en.lower()
    assert appointment_pending_confirmation_message("en") == en
    invite = public_comment_dm_invite("en")
    assert "DM" in invite
    assert "phone" not in invite.lower()


def test_intent_helpers():
    assert looks_like_appointment_intent("I want to book an appointment tomorrow")
    assert looks_like_order_intent("I want to order the serum")


def test_create_after_confirm(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.ai_tool.published_configuration_version", lambda _tid: "v-test")
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-test")
    monkeypatch.setattr(
        "services.requests.ai_tool.load_published_requests_config",
        lambda _tid: {"module_enabled": True, "enabled_types": ["APPOINTMENT"], "fields": []},
    )
    out = execute_create_customer_request(
        {
            "request_type": "APPOINTMENT",
            "customer_confirmed": True,
            "idempotency_key": "idem-ai-0001",
            "title": "Laser Friday",
            "preferred_date": "2026-08-20",
            "preferred_time": "afternoon",
        },
        _ctx(),
        session=req_db,
    )
    assert out["ok"] is True
    assert out["status"] == "NEW"
    assert out["pending_confirmation"] is True
    assert "pending" in out["customer_message_hint"].lower()


def test_create_requires_customer_confirmation(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr(
        "services.requests.ai_tool.load_published_requests_config",
        lambda _tid: {"module_enabled": True, "enabled_types": ["ORDER"], "fields": []},
    )
    out = execute_create_customer_request(
        {
            "request_type": "ORDER",
            "customer_confirmed": False,
            "idempotency_key": "idem-ai-0002",
            "title": "Serum",
        },
        _ctx(source_channel="whatsapp_cloud"),
        session=req_db,
    )
    assert out["ok"] is False
    assert out["error"] == "CUSTOMER_CONFIRMATION_REQUIRED"


def test_setup_inactive_refusal(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: False)
    out = execute_create_customer_request(
        {
            "request_type": "ORDER",
            "customer_confirmed": True,
            "idempotency_key": "idem-ai-0003",
            "title": "Serum",
        },
        _ctx(source_channel="whatsapp_cloud"),
        session=req_db,
    )
    assert out["ok"] is False
    assert out["error"] == "REQUESTS_SETUP_REQUIRED"


def test_idempotency_replay(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.ai_tool.published_configuration_version", lambda _tid: "v-test")
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-test")
    monkeypatch.setattr(
        "services.requests.ai_tool.load_published_requests_config",
        lambda _tid: {"module_enabled": True, "enabled_types": ["ORDER"], "fields": []},
    )
    args = {
        "request_type": "ORDER",
        "customer_confirmed": True,
        "idempotency_key": "idem-ai-replay",
        "title": "Cream",
    }
    first = execute_create_customer_request(args, _ctx(source_channel="whatsapp_cloud"), session=req_db)
    second = execute_create_customer_request(args, _ctx(source_channel="whatsapp_cloud"), session=req_db)
    assert first["ok"] and second["ok"]
    assert first["request_id"] == second["request_id"]


def test_public_comment_refused(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: True)
    out = execute_create_customer_request(
        {
            "request_type": "APPOINTMENT",
            "customer_confirmed": True,
            "idempotency_key": "idem-ai-comment",
            "title": "Book",
        },
        _ctx(public_comment=True),
        session=req_db,
    )
    assert out["ok"] is False
    assert out["error"] == "PUBLIC_COMMENT_REFUSED"


def test_wa_me_not_forced_when_capture_active(monkeypatch):
    from services.social_contact_routing import (
        route_social_contact_request,
        should_force_wa_me_booking_handoff,
    )

    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _tid: True)
    ud = {
        "tenant_id": "tenant-a",
        "channel": "instagram",
        "meta_account_id": "17841413184256533",
        "social_sender_id": "ig-sender-1",
    }
    assert skip_forced_booking_wa_me("tenant-a") is True
    assert should_force_wa_me_booking_handoff("tenant-a", "book appointment") is False
    out = route_social_contact_request("I want to book an appointment", ud, "en")
    assert out is None


def test_wa_me_booking_still_runs_when_capture_inactive(monkeypatch):
    from services.social_contact_routing import route_social_contact_request

    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _tid: False)
    ud = {
        "tenant_id": "linas",
        "channel": "instagram",
        "meta_account_id": "17841413184256533",
        "social_sender_id": "ig-sender-2",
    }
    out = route_social_contact_request("I want to book an appointment", ud, "en")
    assert out is not None
    assert out.intent == "booking"


def test_human_handoff_still_allowed_when_capture_active(monkeypatch):
    from services.social_contact_routing import route_social_contact_request

    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _tid: True)
    ud = {
        "tenant_id": "linas",
        "channel": "instagram",
        "meta_account_id": "17841413184256533",
        "social_sender_id": "ig-sender-3",
    }
    out = route_social_contact_request("I want to speak with a human agent", ud, "en")
    assert out is not None
    assert out.intent == "human"


def _policy_sections_with_handoff_phone() -> dict:
    return {
        "restricted": {"topics": [], "notes": ""},
        "actions": {
            "items": [
                {"id": "human_handoff", "enabled": True},
                {"id": "respond_instagram_comments", "enabled": True},
            ]
        },
        "handoff": {
            "contacts": [
                {
                    "id": "wa1",
                    "destination_type": "whatsapp",
                    "destination_value": "+96178847527",
                    "label": "Team",
                }
            ],
            "matrix": [],
            "policy_text": "",
        },
    }


def test_policy_comment_linked_dm_continues_capture_not_dm_invite(monkeypatch):
    """comment_linked_dm must not be treated as a public comment via substring match."""
    from services.customer_reply_v2.policy import enforce_restricted_and_handoff

    monkeypatch.setattr(
        "services.customer_reply_v2.policy.load_published_content",
        lambda _tid: (object(), _policy_sections_with_handoff_phone()),
    )
    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _tid: True)
    out = enforce_restricted_and_handoff(
        tenant_id="tenant-a",
        message="I want to book an appointment tomorrow",
        response_language="en",
        channel="comment_linked_dm",
    )
    assert out is None


def test_policy_public_comment_never_posts_wa_me(monkeypatch):
    from services.customer_reply_v2.policy import enforce_restricted_and_handoff

    monkeypatch.setattr(
        "services.customer_reply_v2.policy.load_published_content",
        lambda _tid: (object(), _policy_sections_with_handoff_phone()),
    )
    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _tid: False)
    out = enforce_restricted_and_handoff(
        tenant_id="tenant-a",
        message="I want to speak with a human agent",
        response_language="en",
        channel="instagram_comment",
    )
    assert out is not None
    assert out["reason"] == "handoff_public_comment_dm_invite"
    reply = str(out["reply"] or "").lower()
    assert "wa.me" not in reply
    assert "96178847527" not in reply
    assert "dm" in reply
    assert out["metadata"].get("pii_safe_public_comment") is True


def test_policy_public_comment_booking_with_capture_invites_dm(monkeypatch):
    from services.customer_reply_v2.policy import enforce_restricted_and_handoff

    monkeypatch.setattr(
        "services.customer_reply_v2.policy.load_published_content",
        lambda _tid: (object(), _policy_sections_with_handoff_phone()),
    )
    monkeypatch.setattr("services.requests.capture.requests_capture_active", lambda _tid: True)
    out = enforce_restricted_and_handoff(
        tenant_id="tenant-a",
        message="I want to book an appointment tomorrow",
        response_language="en",
        channel="instagram_comment",
    )
    assert out is not None
    assert out["reason"] == "requests_comment_dm_invite"
    reply = str(out["reply"] or "").lower()
    assert "wa.me" not in reply
    assert "phone" not in reply
