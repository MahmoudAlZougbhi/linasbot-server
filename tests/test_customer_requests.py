"""Customer Requests domain tests (SQLite opt-in)."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.schemas import RequestCreateBody  # noqa: E402
from services.requests.service import CustomerRequestsError, CustomerRequestsService  # noqa: E402
from services.requests.state_machine import (  # noqa: E402
    InvalidRequestTransition,
    can_transition,
    require_transition,
    resolve_final_action_status,
)


@pytest.fixture()
def req_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'requests.db'}"
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


def test_appointment_transitions():
    assert can_transition("APPOINTMENT", "NEW", "IN_REVIEW")
    assert can_transition("APPOINTMENT", "IN_REVIEW", "CONFIRMED")
    assert not can_transition("APPOINTMENT", "NEW", "READY")
    with pytest.raises(InvalidRequestTransition):
        require_transition("ORDER", "NEW", "COMPLETED")


def test_final_actions():
    assert resolve_final_action_status("APPOINTMENT", "confirm_appointment") == "CONFIRMED"
    assert resolve_final_action_status("ORDER", "mark_ready") == "READY"
    assert resolve_final_action_status("OTHER", "complete_request") == "COMPLETED"


def test_create_requires_confirmation(req_db, monkeypatch):
    monkeypatch.setattr(
        "services.requests.service.requests_capture_active",
        lambda _tid: True,
    )
    monkeypatch.setattr(
        "services.requests.service.published_configuration_version",
        lambda _tid: "v-test",
    )
    svc = CustomerRequestsService(req_db)
    body = RequestCreateBody(
        request_type="APPOINTMENT",
        source_channel="instagram_dm",
        customer_confirmed=False,
        idempotency_key="idem-key-001",
        title="Laser consult",
    )
    with pytest.raises(CustomerRequestsError) as exc:
        svc.create_from_ai(tenant_id="tenant-a", body=body)
    assert exc.value.code == "CUSTOMER_CONFIRMATION_REQUIRED"


def test_create_list_transition_and_tenant_isolation(req_db, monkeypatch):
    monkeypatch.setattr(
        "services.requests.service.requests_capture_active",
        lambda _tid: True,
    )
    monkeypatch.setattr(
        "services.requests.service.published_configuration_version",
        lambda _tid: "v-test",
    )
    svc = CustomerRequestsService(req_db)
    body = RequestCreateBody(
        request_type="APPOINTMENT",
        source_channel="whatsapp_cloud",
        customer_confirmed=True,
        idempotency_key="idem-key-002",
        title="Preferred Friday",
        preferred_date="2026-08-20",
        preferred_time="afternoon",
        customer_name="Sara",
        conversation_id="conv-1",
    )
    created = svc.create_from_ai(tenant_id="tenant-a", body=body)
    assert created["request_number"] == "REQ-1"
    assert created["status"] == "NEW"
    # idempotent replay
    again = svc.create_from_ai(tenant_id="tenant-a", body=body)
    assert again["request_id"] == created["request_id"]

    listed = svc.list(tenant_id="tenant-a")
    assert len(listed["items"]) == 1
    assert listed["counts"]["NEW"] == 1

    other = svc.list(tenant_id="tenant-b")
    assert other["items"] == []

    with pytest.raises(CustomerRequestsError) as exc:
        svc.get(tenant_id="tenant-b", request_id=created["request_id"], include_sensitive=False)
    assert exc.value.http_status == 404

    updated = svc.transition_status(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        to_status="IN_REVIEW",
        row_version=created["row_version"],
    )
    assert updated["status"] == "IN_REVIEW"
    assert updated["row_version"] == created["row_version"] + 1

    with pytest.raises(CustomerRequestsError) as exc2:
        svc.transition_status(
            tenant_id="tenant-a",
            request_id=created["request_id"],
            actor_user_id="op-1",
            to_status="CONFIRMED",
            row_version=created["row_version"],  # stale
        )
    assert exc2.value.code == "VERSION_CONFLICT"


def test_permission_keys_include_requests():
    from modules.api_security import PERMISSION_KEYS, required_permission_for

    for key in (
        "requests",
        "requestsManage",
        "requestsNotify",
        "requestsManualChat",
        "requestsSensitive",
    ):
        assert key in PERMISSION_KEYS
    assert required_permission_for("GET", "/api/requests") == "requests"
    assert required_permission_for("GET", "/api/requests/abc") == "requests"


def test_list_created_after_filter(req_db, monkeypatch):
    from datetime import UTC, datetime, timedelta

    from db.models.requests import CustomerRequest

    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr(
        "services.requests.service.published_configuration_version",
        lambda _tid: "v-test",
    )
    svc = CustomerRequestsService(req_db)
    old = svc.create_from_ai(
        tenant_id="tenant-a",
        body=RequestCreateBody(
            request_type="OTHER",
            source_channel="instagram_dm",
            customer_confirmed=True,
            idempotency_key="idem-date-old",
            title="old-item",
        ),
    )
    row = req_db.get(CustomerRequest, old["request_id"])
    assert row is not None
    row.created_at = datetime.now(UTC) - timedelta(days=10)
    req_db.commit()
    svc.create_from_ai(
        tenant_id="tenant-a",
        body=RequestCreateBody(
            request_type="OTHER",
            source_channel="instagram_dm",
            customer_confirmed=True,
            idempotency_key="idem-date-new",
            title="new-item",
        ),
    )
    after = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    listed = svc.list(tenant_id="tenant-a", created_after=after)
    assert len(listed["items"]) == 1
    assert listed["items"][0]["title"] == "new-item"
