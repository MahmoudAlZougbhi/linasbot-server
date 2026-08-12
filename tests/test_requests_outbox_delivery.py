"""Tests for Requests outbox channel delivery foundations."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.models.requests_support import CustomerRequestEvent, CustomerRequestOutbox  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.requests.delivery import DeliveryResult, classify_platform_block, redact_delivery_error  # noqa: E402
from services.requests.outbox import process_outbox_item, process_pending_outbox  # noqa: E402
from services.requests.schemas import RequestCreateBody  # noqa: E402
from services.requests.service import CustomerRequestsService  # noqa: E402


@pytest.fixture()
def req_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'outbox.db'}"
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


def _create(session, monkeypatch, *, tenant_id="tenant-a", channel="instagram_dm", key="idem-out-1"):
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _t: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _t: "v1")
    svc = CustomerRequestsService(session)
    return svc.create_from_ai(
        tenant_id=tenant_id,
        body=RequestCreateBody(
            request_type="ORDER",
            source_channel=channel,
            customer_confirmed=True,
            idempotency_key=key,
            source_account_id="page-1",
            external_customer_id="psid-1",
            conversation_id="conv-ig-1",
            title="Outbox order",
        ),
    )


@pytest.mark.asyncio
async def test_outbox_idempotent_enqueue_and_send(req_db, monkeypatch):
    created = _create(req_db, monkeypatch)
    svc = CustomerRequestsService(req_db)
    # Move to READY with notification
    svc.transition_status(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        to_status="IN_REVIEW",
        row_version=created["row_version"],
    )
    mid = svc.get(tenant_id="tenant-a", request_id=created["request_id"], include_sensitive=False)
    svc.transition_status(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        to_status="CONFIRMED",
        row_version=mid["row_version"],
    )
    mid2 = svc.get(tenant_id="tenant-a", request_id=created["request_id"], include_sensitive=False)
    ready = svc.final_action(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        actor_user_id="op-1",
        action="mark_ready",
        row_version=mid2["row_version"],
        completion_message="Ready for pickup",
        idempotency_key="final-ready-001",
        send_notification=True,
    )
    assert ready["notification_status"] == "pending"

    outboxes = list(
        req_db.execute(
            select(CustomerRequestOutbox).where(CustomerRequestOutbox.request_id == created["request_id"])
        ).scalars()
    )
    assert len(outboxes) == 1
    assert outboxes[0].channel == "instagram_dm"

    # Duplicate enqueue same key returns same row
    again = svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="notify:final-ready-001",
        channel="instagram_dm",
        payload={"message": "Ready for pickup"},
    )
    assert again.id == outboxes[0].id

    async def _fake_deliver(**kwargs):
        assert kwargs["channel"] == "instagram_dm"
        return DeliveryResult(status="sent", channel_used="instagram_dm", provider_message_id="m1")

    results = await process_pending_outbox(
        req_db, tenant_id="tenant-a", request_id=created["request_id"], deliver=_fake_deliver
    )
    assert len(results) == 1
    assert results[0].status == "sent"

    refreshed = svc.get(tenant_id="tenant-a", request_id=created["request_id"], include_sensitive=False)
    assert refreshed["notification_status"] == "sent"

    # Reprocess is skipped (idempotent terminal)
    item = req_db.get(CustomerRequestOutbox, outboxes[0].id)
    skipped = await process_outbox_item(req_db, item, deliver=_fake_deliver)
    assert skipped.skipped is True
    assert skipped.status == "sent"


@pytest.mark.asyncio
async def test_no_cross_channel_switch(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, channel="facebook_messenger", key="idem-fb-1")
    svc = CustomerRequestsService(req_db)
    row = svc.repo.get_for_tenant(tenant_id="tenant-a", request_id=created["request_id"])
    outbox = svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="notify-fb-1",
        channel="facebook_messenger",
        payload={"message": "hi"},
    )
    row.notification_status = "pending"
    req_db.commit()

    async def _evil_switch(**kwargs):
        # Attempt to deliver on WhatsApp instead of Facebook — must be rejected.
        return DeliveryResult(status="sent", channel_used="whatsapp_cloud", provider_message_id="x")

    result = await process_outbox_item(req_db, outbox, deliver=_evil_switch)
    req_db.commit()
    assert result.status == "failed"
    assert result.error_redacted == "cross_channel_switch_rejected"
    req_db.refresh(row)
    assert row.notification_status == "failed"


@pytest.mark.asyncio
async def test_channel_mismatch_on_outbox_vs_request(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, channel="instagram_dm", key="idem-mis-1")
    svc = CustomerRequestsService(req_db)
    row = svc.repo.get_for_tenant(tenant_id="tenant-a", request_id=created["request_id"])
    outbox = svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="bad-channel",
        channel="whatsapp_cloud",  # mismatched vs request
        payload={"message": "x"},
    )
    row.notification_status = "pending"
    req_db.commit()

    async def _never(**kwargs):
        raise AssertionError("must not deliver on mismatched channel")

    result = await process_outbox_item(req_db, outbox, deliver=_never)
    assert result.status == "failed"
    assert result.error_redacted == "channel_mismatch_no_switch"


@pytest.mark.asyncio
async def test_blocked_status(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, key="idem-block-1")
    svc = CustomerRequestsService(req_db)
    row = svc.repo.get_for_tenant(tenant_id="tenant-a", request_id=created["request_id"])
    outbox = svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="block-1",
        channel="instagram_dm",
        payload={"message": "hi"},
    )
    row.notification_status = "pending"
    req_db.commit()

    async def _blocked(**kwargs):
        return DeliveryResult(status="blocked", channel_used="instagram_dm", error_redacted="code=551")

    result = await process_outbox_item(req_db, outbox, deliver=_blocked)
    req_db.commit()
    assert result.status == "blocked"
    req_db.refresh(row)
    assert row.notification_status == "blocked"
    events = list(
        req_db.execute(
            select(CustomerRequestEvent).where(
                CustomerRequestEvent.request_id == created["request_id"],
                CustomerRequestEvent.event_type == "DELIVERY_BLOCKED_BY_PLATFORM",
            )
        ).scalars()
    )
    assert len(events) == 1


@pytest.mark.asyncio
async def test_tenant_isolation_outbox(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, tenant_id="tenant-a", key="idem-iso-1")
    svc = CustomerRequestsService(req_db)
    svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="iso-1",
        channel="instagram_dm",
        payload={"message": "hi"},
    )
    req_db.commit()
    other = await process_pending_outbox(req_db, tenant_id="tenant-b", limit=10)
    assert other == []


def test_claim_pending_outbox_marks_processing_and_exclusive(req_db, monkeypatch):
    created = _create(req_db, monkeypatch, key="idem-claim-1")
    svc = CustomerRequestsService(req_db)
    svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="claim-1",
        channel="instagram_dm",
        payload={"message": "hi"},
    )
    req_db.commit()

    repo = svc.repo
    claimed = repo.claim_pending_outbox(tenant_id="tenant-a", limit=10)
    assert len(claimed) == 1
    assert claimed[0].status == "processing"
    assert claimed[0].attempts == 1
    assert claimed[0].claimed_at is not None

    again = repo.claim_pending_outbox(tenant_id="tenant-a", limit=10)
    assert again == []


def test_claim_pending_outbox_reclaims_stale_processing(req_db, monkeypatch):
    from datetime import UTC, datetime, timedelta

    created = _create(req_db, monkeypatch, key="idem-claim-stale")
    svc = CustomerRequestsService(req_db)
    svc.repo.enqueue_outbox(
        tenant_id="tenant-a",
        request_id=created["request_id"],
        idempotency_key="claim-stale",
        channel="instagram_dm",
        payload={"message": "hi"},
    )
    req_db.commit()
    repo = svc.repo
    claimed = repo.claim_pending_outbox(tenant_id="tenant-a", limit=10, reclaim_stale_seconds=0)
    assert len(claimed) == 1
    claimed[0].claimed_at = datetime.now(UTC) - timedelta(seconds=600)
    req_db.flush()

    reclaimed = repo.claim_pending_outbox(tenant_id="tenant-a", limit=10, reclaim_stale_seconds=60)
    assert len(reclaimed) == 1
    assert reclaimed[0].status == "processing"
    assert int(reclaimed[0].attempts or 0) >= 2

def test_redact_and_classify():
    assert "credential_or_auth_error" in redact_delivery_error("Authorization: Bearer SECRET")
    assert classify_platform_block(channel="instagram_dm", error_code=551, message="")
    assert classify_platform_block(channel="whatsapp_cloud", error_code="131026", message="")
    assert not classify_platform_block(channel="whatsapp_cloud", error_code="500", message="timeout")


def test_comment_linked_binding_resolves_facebook():
    from types import SimpleNamespace

    from services.requests.delivery import _meta_bindings_for_account

    class _Reg:
        def list_bindings(self, include_inactive=False):
            return [
                SimpleNamespace(
                    tenant_id="tenant-a",
                    channel="facebook",
                    asset_id="page-fb-1",
                    page_id="page-fb-1",
                    instagram_account_id=None,
                    active=True,
                )
            ]

    found = _meta_bindings_for_account(
        _Reg(), tenant_id="tenant-a", account="page-fb-1", meta_channels=("instagram", "facebook")
    )
    assert len(found) == 1
    assert found[0].channel == "facebook"
