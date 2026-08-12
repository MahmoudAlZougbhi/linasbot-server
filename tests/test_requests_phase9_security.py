"""Phase 9: Customer Requests security and correctness (SQLite opt-in).

Focused contracts (tenant isolation, concurrency, transitions, AI refusal,
RBAC path gate, outbox notify-retry idempotency). BOC zero-HTTP coverage
lives in tests/test_boc_booking_isolation.py — not duplicated here.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.models.requests_support import CustomerRequestOutbox  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from modules.api_security import (  # noqa: E402
    PERMISSION_KEYS,
    SYSTEM_ROLE_PERMISSIONS,
    required_permission_for,
    resolve_permissions,
    user_has_permission,
)
from services.dashboard_session_service import SessionRecord  # noqa: E402
from services.requests.ai_tool import AiToolContext, execute_create_customer_request  # noqa: E402
from services.requests.constants import REQUEST_PERMISSION_KEYS  # noqa: E402
from services.requests.schemas import RequestCreateBody  # noqa: E402
from services.requests.service import CustomerRequestsError, CustomerRequestsService  # noqa: E402


@pytest.fixture()
def req_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'requests_phase9.db'}"
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


def _enable_capture(monkeypatch) -> None:
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-phase9")


def _create(
    session,
    monkeypatch,
    *,
    tenant_id: str = "tenant-a",
    request_type: str = "APPOINTMENT",
    channel: str = "instagram_dm",
    key: str = "idem-p9-1",
    customer_confirmed: bool = True,
    **extra,
) -> dict:
    _enable_capture(monkeypatch)
    svc = CustomerRequestsService(session)
    body = RequestCreateBody(
        request_type=request_type,
        source_channel=channel,
        customer_confirmed=customer_confirmed,
        idempotency_key=key,
        title=extra.pop("title", "Phase9 request"),
        phone_normalized=extra.pop("phone_normalized", None),
        email=extra.pop("email", None),
        delivery_address=extra.pop("delivery_address", None),
        **extra,
    )
    return svc.create_from_ai(tenant_id=tenant_id, body=body)


# --- Tenant isolation -------------------------------------------------------


def test_get_wrong_tenant_returns_404(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, key="idem-p9-iso-get")
    svc = CustomerRequestsService(req_db)
    with pytest.raises(CustomerRequestsError) as exc:
        svc.get(tenant_id="tenant-b", request_id=created["request_id"], include_sensitive=False)
    assert exc.value.code == "NOT_FOUND"
    assert exc.value.http_status == 404


def test_list_wrong_tenant_empty(req_db, monkeypatch):
    _create(req_db, monkeypatch, key="idem-p9-iso-list")
    svc = CustomerRequestsService(req_db)
    other = svc.list(tenant_id="tenant-b")
    assert other["items"] == []
    assert other["counts"].get("NEW", 0) == 0


def test_transition_wrong_tenant_404(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, key="idem-p9-iso-tr")
    svc = CustomerRequestsService(req_db)
    with pytest.raises(CustomerRequestsError) as exc:
        svc.transition_status(
            tenant_id="tenant-b",
            request_id=created["request_id"],
            actor_user_id="op-1",
            to_status="IN_REVIEW",
            row_version=created["row_version"],
        )
    assert exc.value.http_status == 404
    # Original row unchanged
    owned = svc.get(tenant_id="tenant-a", request_id=created["request_id"], include_sensitive=False)
    assert owned["status"] == "NEW"
    assert owned["row_version"] == created["row_version"]


# --- Optimistic concurrency -------------------------------------------------


def test_stale_row_version_conflict_409(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, key="idem-p9-ver")
    svc = CustomerRequestsService(req_db)
    first = svc.transition_status(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        to_status="IN_REVIEW",
        row_version=created["row_version"],
    )
    assert first["row_version"] == created["row_version"] + 1

    with pytest.raises(CustomerRequestsError) as exc:
        svc.transition_status(
            tenant_id="tenant-a",
            request_id=created["request_id"],
            actor_user_id="op-2",
            to_status="CONFIRMED",
            row_version=created["row_version"],  # stale
        )
    assert exc.value.code == "VERSION_CONFLICT"
    assert exc.value.http_status == 409


# --- Invalid status transitions ---------------------------------------------


def test_invalid_appointment_transition_refused(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, request_type="APPOINTMENT", key="idem-p9-bad-appt")
    svc = CustomerRequestsService(req_db)
    with pytest.raises(CustomerRequestsError) as exc:
        svc.transition_status(
            tenant_id="tenant-a",
            request_id=created["request_id"],
            actor_user_id="op-1",
            to_status="READY",  # ORDER-only path
            row_version=created["row_version"],
        )
    assert exc.value.code == "INVALID_TRANSITION"


def test_invalid_order_skip_to_ready_refused(req_db, monkeypatch):
    created = _create(
        req_db, monkeypatch, request_type="ORDER", channel="whatsapp_cloud", key="idem-p9-bad-ord"
    )
    svc = CustomerRequestsService(req_db)
    with pytest.raises(CustomerRequestsError) as exc:
        svc.transition_status(
            tenant_id="tenant-a",
            request_id=created["request_id"],
            actor_user_id="op-1",
            to_status="READY",  # must pass CONFIRMED first
            row_version=created["row_version"],
        )
    assert exc.value.code == "INVALID_TRANSITION"


def test_wrong_final_action_for_type_refused(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, request_type="APPOINTMENT", key="idem-p9-bad-final")
    svc = CustomerRequestsService(req_db)
    mid = svc.transition_status(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        to_status="IN_REVIEW",
        row_version=created["row_version"],
    )
    with pytest.raises(CustomerRequestsError) as exc:
        svc.final_action(
            tenant_id="tenant-a",
            request_id=created["request_id"],
            actor_user_id="op-1",
            action="mark_ready",  # ORDER action on APPOINTMENT
            row_version=mid["row_version"],
            completion_message=None,
            idempotency_key="final-bad-1",
            send_notification=False,
        )
    assert exc.value.code == "INVALID_TRANSITION"


# --- Create confirmation gate -----------------------------------------------


def test_create_without_customer_confirmed_refused(req_db, monkeypatch):
    _enable_capture(monkeypatch)
    svc = CustomerRequestsService(req_db)
    body = RequestCreateBody(
        request_type="ORDER",
        source_channel="whatsapp_cloud",
        customer_confirmed=False,
        idempotency_key="idem-p9-noconfirm",
        title="Serum",
    )
    with pytest.raises(CustomerRequestsError) as exc:
        svc.create_from_ai(tenant_id="tenant-a", body=body)
    assert exc.value.code == "CUSTOMER_CONFIRMATION_REQUIRED"


# --- AI tool public comment -------------------------------------------------


def test_ai_tool_public_comment_refused(req_db, monkeypatch):
    monkeypatch.setattr("services.requests.ai_tool.requests_capture_active", lambda _tid: True)
    out = execute_create_customer_request(
        {
            "request_type": "APPOINTMENT",
            "customer_confirmed": True,
            "idempotency_key": "idem-p9-comment",
            "title": "Book from comment",
        },
        AiToolContext(
            tenant_id="tenant-a",
            source_channel="instagram_dm",
            conversation_id="conv-c1",
            response_language="en",
            public_comment=True,
        ),
        session=req_db,
    )
    assert out["ok"] is False
    assert out["error"] == "PUBLIC_COMMENT_REFUSED"


# --- Sensitive field redaction ----------------------------------------------


def test_get_omits_sensitive_without_flag(req_db, monkeypatch):
    created = _create(
        req_db,
        monkeypatch,
        key="idem-p9-pii",
        phone_normalized="+96170000000",
        email="sara@example.com",
        delivery_address="Beirut",
    )
    svc = CustomerRequestsService(req_db)
    public = svc.get(tenant_id="tenant-a", request_id=created["request_id"], include_sensitive=False)
    assert "phone_normalized" not in public
    assert "email" not in public
    assert "delivery_address" not in public
    assert public["phone_present"] is True
    assert public["email_present"] is True
    assert public["delivery_address_present"] is True

    private = svc.get(tenant_id="tenant-a", request_id=created["request_id"], include_sensitive=True)
    assert private["phone_normalized"] == "+96170000000"
    assert private["email"] == "sara@example.com"


# --- Notification outbox notify-retry idempotency ---------------------------


def test_notify_retry_idempotent_outbox(req_db, monkeypatch):
    created = _create(
        req_db, monkeypatch, request_type="ORDER", channel="instagram_dm", key="idem-p9-retry"
    )
    svc = CustomerRequestsService(req_db)
    first = svc.retry_notification(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        idempotency_key="retry-key-p9",
    )
    assert first["notification_status"] == "pending"
    second = svc.retry_notification(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        idempotency_key="retry-key-p9",
    )
    assert second["notification_status"] == "pending"
    rows = list(
        req_db.execute(
            select(CustomerRequestOutbox).where(CustomerRequestOutbox.request_id == created["request_id"])
        ).scalars()
    )
    assert len(rows) == 1
    assert rows[0].idempotency_key == "retry-key-p9"


# --- Permission path gate ---------------------------------------------------


def test_api_requests_path_requires_requests_permission():
    assert "requests" in PERMISSION_KEYS
    for key in REQUEST_PERMISSION_KEYS:
        assert key in PERMISSION_KEYS

    assert required_permission_for("GET", "/api/requests") == "requests"
    assert required_permission_for("GET", "/api/requests/") == "requests"
    assert required_permission_for("GET", "/api/requests/abc-123") == "requests"
    assert required_permission_for("POST", "/api/requests/abc/assign") == "requests"
    assert required_permission_for("POST", "/api/requests/abc/notify-retry") == "requests"
    assert required_permission_for("POST", "/api/requests/abc/manual-mode/resume") == "requests"


def _session(*, role: str, user_id: str = "u1") -> SessionRecord:
    return SessionRecord(
        session_id=f"s-{role}",
        user_id=user_id,
        email=f"{role}@example.com",
        role=role,
        permissions=None,
        tenant_id="tenant-a",
        csrf_token="csrf",
        created_at=0.0,
        expires_at=9_999_999_999.0,
    )


def test_viewer_lacks_requests_operator_has_base_keys():
    viewer = _session(role="viewer", user_id="u-v")
    operator = _session(role="operator", user_id="u-o")
    assert user_has_permission(viewer, "requests") is False
    assert user_has_permission(operator, "requests") is True
    assert user_has_permission(operator, "requestsManage") is True
    assert user_has_permission(operator, "requestsSensitive") is False
    assert SYSTEM_ROLE_PERMISSIONS["operator"]["requests"] is True
    assert resolve_permissions("viewer", None)["requests"] is False
