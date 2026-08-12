"""Tests for Requests manual mode pause/resume and race guards."""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"
os.environ.setdefault("META_CREDENTIAL_ENCRYPTION_KEY", "x" * 32)

from db.models import Base  # noqa: E402
from db.models.requests_support import CustomerRequestEvent  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.manual_mode import activate_manual_mode, resume_manual_mode  # noqa: E402
from services.requests.schemas import RequestCreateBody  # noqa: E402
from services.requests.service import CustomerRequestsError, CustomerRequestsService  # noqa: E402
from services.whatsapp_cloud.repository import WhatsAppCloudRepository  # noqa: E402


@pytest.fixture()
def req_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'manual_mode.db'}"
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


def _seed_wa_conversation(session, *, tenant_id: str = "tenant-a"):
    repo = WhatsAppCloudRepository(session)
    conn = repo.create_connection_with_credential(
        tenant_id=tenant_id,
        created_by_user_id="u1",
        meta_app_key="linas_first_party",
        meta_app_id="2963733803971681",
        waba_id="111",
        phone_number_id="999100",
        display_phone_number="+96171111999",
        verified_name="Clinic",
        access_token="token-a",
        scopes=["whatsapp_business_management", "whatsapp_business_messaging"],
    )
    conv = repo.get_or_create_conversation(
        tenant_id=tenant_id,
        connection_id=conn.id,
        customer_wa_id="96170000001",
        profile_name="Sara",
    )
    session.commit()
    return conn, conv


def _create_request(session, *, tenant_id: str, conversation_id: str, monkeypatch):
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _t: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _t: "v1")
    svc = CustomerRequestsService(session)
    return svc.create_from_ai(
        tenant_id=tenant_id,
        body=RequestCreateBody(
            request_type="ORDER",
            source_channel="whatsapp_cloud",
            customer_confirmed=True,
            idempotency_key="idem-manual-001",
            conversation_id=conversation_id,
            title="Order test",
        ),
    )


@pytest.mark.asyncio
async def test_pause_on_activate_bumps_epoch_and_audits(req_db, monkeypatch):
    _, conv = _seed_wa_conversation(req_db)
    created = _create_request(req_db, tenant_id="tenant-a", conversation_id=conv.id, monkeypatch=monkeypatch)

    with patch("services.requests.manual_mode._pause_firestore", new_callable=AsyncMock) as firestore_pause:
        firestore_pause.return_value = True
        result = await activate_manual_mode(
            conversation_id=conv.id,
            user_id="whatsapp:96170000001",
            actor_user_id="op-1",
            tenant_id="tenant-a",
            request_id=created["request_id"],
            source_channel="whatsapp_cloud",
            session=req_db,
        )
        req_db.commit()

    assert result.activated is True
    assert result.control_epoch is not None and result.control_epoch >= 2
    assert result.audit_recorded is True

    req_db.refresh(conv)
    assert conv.control_state == "HUMAN_PAUSED"

    events = list(
        req_db.execute(
            select(CustomerRequestEvent).where(
                CustomerRequestEvent.request_id == created["request_id"],
                CustomerRequestEvent.event_type == "manual_pause",
            )
        ).scalars()
    )
    assert len(events) == 1
    assert events[0].actor_user_id == "op-1"

    # Idempotent second activate — no second audit
    with patch("services.requests.manual_mode._pause_firestore", new_callable=AsyncMock):
        again = await activate_manual_mode(
            conversation_id=conv.id,
            user_id="whatsapp:96170000001",
            actor_user_id="op-1",
            tenant_id="tenant-a",
            request_id=created["request_id"],
            source_channel="whatsapp_cloud",
            session=req_db,
        )
        req_db.commit()
    assert again.already_active is True
    assert again.audit_recorded is False
    events2 = list(
        req_db.execute(
            select(CustomerRequestEvent).where(
                CustomerRequestEvent.request_id == created["request_id"],
                CustomerRequestEvent.event_type == "manual_pause",
            )
        ).scalars()
    )
    assert len(events2) == 1


@pytest.mark.asyncio
async def test_resume_clears_pause_idempotent(req_db, monkeypatch):
    _, conv = _seed_wa_conversation(req_db)
    created = _create_request(req_db, tenant_id="tenant-a", conversation_id=conv.id, monkeypatch=monkeypatch)
    with patch("services.requests.manual_mode._pause_firestore", new_callable=AsyncMock):
        await activate_manual_mode(
            conversation_id=conv.id,
            user_id="whatsapp:96170000001",
            actor_user_id="op-1",
            tenant_id="tenant-a",
            request_id=created["request_id"],
            source_channel="whatsapp_cloud",
            session=req_db,
        )
        req_db.commit()

    with patch("services.requests.manual_mode._resume_firestore", new_callable=AsyncMock):
        resumed = await resume_manual_mode(
            conversation_id=conv.id,
            user_id="whatsapp:96170000001",
            actor_user_id="op-1",
            tenant_id="tenant-a",
            request_id=created["request_id"],
            source_channel="whatsapp_cloud",
            session=req_db,
        )
        req_db.commit()
    assert resumed.control_epoch is not None
    req_db.refresh(conv)
    assert conv.control_state == "AI_ACTIVE"

    with patch("services.requests.manual_mode._resume_firestore", new_callable=AsyncMock):
        again = await resume_manual_mode(
            conversation_id=conv.id,
            user_id="whatsapp:96170000001",
            actor_user_id="op-1",
            tenant_id="tenant-a",
            request_id=created["request_id"],
            source_channel="whatsapp_cloud",
            session=req_db,
        )
        req_db.commit()
    assert again.already_active is True
    assert again.audit_recorded is False


@pytest.mark.asyncio
async def test_manual_mode_tenant_isolation(req_db, monkeypatch):
    _, conv = _seed_wa_conversation(req_db, tenant_id="tenant-a")
    created = _create_request(req_db, tenant_id="tenant-a", conversation_id=conv.id, monkeypatch=monkeypatch)
    with patch("services.requests.manual_mode._pause_firestore", new_callable=AsyncMock):
        with pytest.raises(PermissionError):
            await activate_manual_mode(
                conversation_id=conv.id,
                user_id="whatsapp:96170000001",
                actor_user_id="op-x",
                tenant_id="tenant-b",
                request_id=created["request_id"],
                source_channel="whatsapp_cloud",
                session=req_db,
            )


@pytest.mark.asyncio
async def test_epoch_race_suppresses_in_flight_ai(req_db):
    """If manual mode wins first, AI send path sees epoch mismatch (existing WA guard)."""
    _, conv = _seed_wa_conversation(req_db)
    expected_epoch = int(conv.control_epoch)
    with patch("services.requests.manual_mode._pause_firestore", new_callable=AsyncMock):
        await activate_manual_mode(
            conversation_id=conv.id,
            user_id="whatsapp:96170000001",
            actor_user_id="op-1",
            tenant_id="tenant-a",
            source_channel="whatsapp_cloud",
            session=req_db,
        )
        req_db.commit()
    req_db.refresh(conv)
    assert conv.control_state == "HUMAN_PAUSED"
    assert int(conv.control_epoch) != expected_epoch
    # Mirror ai_bridge race check
    assert not (conv.control_state == "AI_ACTIVE" and int(conv.control_epoch) == expected_epoch)


@pytest.mark.asyncio
async def test_requires_authenticated_actor(req_db):
    with pytest.raises(ValueError, match="actor_user_id"):
        await activate_manual_mode(
            conversation_id="c1",
            user_id="u1",
            actor_user_id="",
            tenant_id="tenant-a",
            session=req_db,
        )


def test_wrong_tenant_request_get(req_db, monkeypatch):
    _, conv = _seed_wa_conversation(req_db)
    created = _create_request(req_db, tenant_id="tenant-a", conversation_id=conv.id, monkeypatch=monkeypatch)
    svc = CustomerRequestsService(req_db)
    with pytest.raises(CustomerRequestsError) as exc:
        svc.get(tenant_id="tenant-b", request_id=created["request_id"], include_sensitive=False)
    assert exc.value.http_status == 404
