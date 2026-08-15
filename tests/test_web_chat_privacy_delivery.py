"""Website Chat privacy, session authority, HA delivery, and poll/ack tests."""

from __future__ import annotations

import os
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
os.environ.setdefault("WEB_CHAT_ALLOW_FILE_STORE", "true")

from db.models.base import Base  # noqa: E402
from db.session import reset_engine_for_tests  # noqa: E402
from services.web_chat.config_models import WebChatWidgetConfig  # noqa: E402
from services.web_chat.delivery_outbox import ack_pending_messages, poll_pending_messages  # noqa: E402
from services.web_chat.ha_repository import WebChatHaRepository  # noqa: E402
from services.web_chat.public_handlers import bootstrap_visitor_session, send_visitor_message  # noqa: E402
from services.web_chat.session_authority import (  # noqa: E402
    SessionAuthorityError,
    hash_session_authority,
    issue_session_authority,
    verify_session_binding,
)
from services.web_chat.store import WebChatStore  # noqa: E402
from tests.web_chat_acceptance_support import seed_widget_config  # noqa: E402


@pytest.fixture()
def web_store(tmp_path, monkeypatch):
    store = WebChatStore(root=tmp_path / "web_chat")
    monkeypatch.setattr("services.web_chat.store.web_chat_store", store)
    monkeypatch.setattr("services.web_chat.public_handlers.web_chat_store", store)
    monkeypatch.setattr("services.web_chat.delivery_outbox.web_chat_store", store)
    return store


@pytest.fixture()
def ha_db(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'web_chat_ha.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.delenv("WEB_CHAT_ALLOW_FILE_STORE", raising=False)
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    yield engine
    reset_engine_for_tests()


def _widget(tenant: str = "biz", key: str = "wk123456789012345678901234") -> WebChatWidgetConfig:
    return WebChatWidgetConfig(
        tenant_id=tenant,
        widget_key=key,
        site_url="https://shop.example.com",
        enabled=True,
        created_at=time.time(),
        updated_at=time.time(),
    )


def test_server_issues_session_authority_bound_to_widget() -> None:
    widget = _widget()
    bundle = issue_session_authority(widget=widget)
    assert len(bundle.session_id) >= 16
    assert len(bundle.authority_token) >= 32
    verify_session_binding(
        session_tenant_id=widget.tenant_id,
        session_widget_key=widget.widget_key,
        authority_hash=bundle.authority_hash,
        widget=widget,
        presented_authority=bundle.authority_token,
    )


def test_stolen_session_id_cross_tenant_rejected(web_store) -> None:
    widget_a = _widget("tenant-a", "wk-aaaaaaaaaaaaaaaaaaaaaaaa")
    widget_b = _widget("tenant-b", "wk-bbbbbbbbbbbbbbbbbbbbbbbb")
    bundle = issue_session_authority(widget=widget_a)
    web_store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget_a,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    with pytest.raises(SessionAuthorityError) as exc:
        verify_session_binding(
            session_tenant_id=widget_a.tenant_id,
            session_widget_key=widget_a.widget_key,
            authority_hash=bundle.authority_hash,
            widget=widget_b,
            presented_authority=bundle.authority_token,
        )
    assert exc.value.code == "SESSION_BOUNDARY"


def test_filename_collision_sanitization_does_not_merge_sessions(web_store) -> None:
    widget = _widget()
    sid_a = "tenant/collision?test"
    sid_b = "tenant_collision_test"
    with pytest.raises(ValueError):
        web_store.get_or_create_visitor(session_id=sid_a, widget=widget, greeting="A", authority_hash="h1")
    session_b = web_store.get_or_create_visitor(session_id=sid_b, widget=widget, greeting="B", authority_hash="h2")
    assert session_b.id == sid_b
    assert web_store.get_visitor(sid_a) is None


@pytest.mark.asyncio
async def test_bootstrap_returns_server_authority(web_store, monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    monkeypatch.setattr(
        "services.web_chat.public_handlers.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    widget = _widget()
    out = await bootstrap_visitor_session(widget=widget, store=web_store)
    assert out["session_authority"]
    assert out["session_id"]
    visitor = web_store.get_visitor(out["session_id"])
    assert visitor is not None
    assert visitor.authority_hash == hash_session_authority(out["session_authority"])


@pytest.mark.asyncio
async def test_send_rejects_wrong_authority(web_store, monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    widget = _widget()
    bundle = issue_session_authority(widget=widget)
    web_store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    with pytest.raises(SessionAuthorityError):
        await send_visitor_message(
            widget=widget,
            session_id=bundle.session_id,
            session_authority="wrong-token",
            content="Hello",
            store=web_store,
        )


def test_poll_and_ack_cursor_idempotent(web_chat_pg_store) -> None:
    store = web_chat_pg_store
    widget = seed_widget_config(store, _widget())
    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    store.queue_assistant_message(bundle.session_id, "Follow up 1", idempotency_key="m1")
    store.queue_assistant_message(bundle.session_id, "Follow up 2", idempotency_key="m2")

    first = poll_pending_messages(
        session_id=bundle.session_id,
        widget=widget,
        session_authority=bundle.authority_token,
        store=store,
    )
    assert len(first["messages"]) == 2

    ack_pending_messages(
        session_id=bundle.session_id,
        widget=widget,
        session_authority=bundle.authority_token,
        message_ids=["m1"],
        store=store,
    )
    second = poll_pending_messages(
        session_id=bundle.session_id,
        widget=widget,
        session_authority=bundle.authority_token,
        cursor="m1",
        store=store,
    )
    assert len(second["messages"]) == 1
    assert second["messages"][0]["id"] == "m2"

    visitor = store.get_visitor(bundle.session_id)
    assert visitor is not None
    assert len(visitor.pending_assistant) == 1


def test_ha_idempotency_two_nodes(ha_db, tmp_path, monkeypatch) -> None:
    repo = WebChatHaRepository()
    Session = sessionmaker(bind=ha_db, autoflush=False, autocommit=False, future=True)

    with Session() as db:
        repo.create_session(
            db,
            session_id="visitor-ha",
            tenant_id="biz",
            widget_key="wk-ha",
            authority_hash="hash1",
            greeting="Hi",
        )
        first = repo.claim_idempotency(
            db, tenant_id="biz", session_id="visitor-ha", idempotency_key="idem-x", message_id="idem-x"
        )
        db.commit()
    with Session() as db:
        second = repo.claim_idempotency(
            db, tenant_id="biz", session_id="visitor-ha", idempotency_key="idem-x", message_id="idem-x"
        )
        db.commit()
    assert first is True
    assert second is False


def test_legacy_session_rejected_when_ha_required(web_store, ha_db, monkeypatch) -> None:
    monkeypatch.delenv("WEB_CHAT_ALLOW_FILE_STORE", raising=False)
    widget = _widget()
    web_store.get_or_create_visitor(session_id="legacy-session1", widget=widget, greeting="Hi", authority_hash="")
    with pytest.raises(SessionAuthorityError) as exc:
        poll_pending_messages(
            session_id="legacy-session1",
            widget=widget,
            session_authority="any",
            store=web_store,
        )
    assert exc.value.code == "LEGACY_SESSION_REJECTED"


def test_disabled_widget_rejected() -> None:
    widget = _widget()
    widget.enabled = False
    from services.web_chat.flags import assert_widget_operational

    with pytest.raises(ValueError):
        assert_widget_operational(widget)


@pytest.mark.asyncio
async def test_capture_failure_does_not_append_turn(web_chat_pg_store, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    from tests.web_chat_acceptance_billing import seed_acceptance_credit_ledger, wire_pg_billing_stores
    from tests.web_chat_acceptance_support import patch_acceptance_eligibility, patch_ai_reply

    wire_pg_billing_stores(monkeypatch)
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    seed_acceptance_credit_ledger(tenant_id="biz", plan_id="max")
    patch_ai_reply(monkeypatch, reply="AI reply")
    store = web_chat_pg_store
    widget = seed_widget_config(store, _widget())
    bundle = issue_session_authority(widget=widget)
    visitor = store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    from services.credit_ledger_service import credit_ledger_service
    from services.web_chat.persistence import PersistOutcome, PersistResult
    from services.web_chat.processor import WebChatError, process_web_chat_message

    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(return_value=PersistResult(outcome=PersistOutcome.CREATED, conversation_id="conv")),
    )
    monkeypatch.setattr(
        credit_ledger_service,
        "capture",
        MagicMock(side_effect=RuntimeError("capture failed")),
    )

    with pytest.raises(WebChatError) as exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hello",
            store=store,
            idempotency_key="capture-fail-privacy",
        )
    assert exc.value.code == "credit_capture_failed"
    refreshed = store.get_visitor(bundle.session_id)
    assert refreshed is not None
    assert len(refreshed.messages) == 1


@pytest.mark.asyncio
async def test_queue_failure_after_persist_recovers(web_chat_pg_store, monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    from services.web_chat.followup_delivery import deliver_web_followup_message
    from services.web_chat.processor import compose_web_user_id
    from tests.test_web_followup_web_delivery import _reserve_followup_credit

    store = web_chat_pg_store
    widget = seed_widget_config(store, _widget())
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id="visitor-queue",
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    save_mock = AsyncMock(return_value=MagicMock(outcome="created", conversation_id="conv"))
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", save_mock)

    attempts = 0
    original_queue = store.queue_assistant_message

    def queue_once_then_succeed(session_id: str, content: str, *, idempotency_key: str | None = None) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("queue failed after persist")
        return original_queue(session_id, content, idempotency_key=idempotency_key)

    monkeypatch.setattr(store, "queue_assistant_message", queue_once_then_succeed)

    reservation_id = _reserve_followup_credit(tenant_id=widget.tenant_id, idem="sfu:queue:1")

    with pytest.raises(RuntimeError, match="queue failed"):
        await deliver_web_followup_message(
            tenant_id=widget.tenant_id,
            visitor_id="visitor-queue",
            user_id=compose_web_user_id("visitor-queue"),
            conversation_id=f"web:{widget.tenant_id}:visitor-queue",
            reply_text="Checking in",
            idempotency_key="sfu:queue:1",
            widget_key=widget.widget_key,
            store=store,
            reservation_id=reservation_id,
        )
    recovered = await deliver_web_followup_message(
        tenant_id=widget.tenant_id,
        visitor_id="visitor-queue",
        user_id=compose_web_user_id("visitor-queue"),
        conversation_id=f"web:{widget.tenant_id}:visitor-queue",
        reply_text="Checking in",
        idempotency_key="sfu:queue:1",
        widget_key=widget.widget_key,
        store=store,
        reservation_id=reservation_id,
    )
    assert recovered.status == "delivered"
    session = store.get_visitor("visitor-queue")
    assert session is not None
    assert len(session.pending_assistant) == 1


def test_two_widget_sessions_are_isolated(web_store) -> None:
    widget_a = _widget("tenant-a", "wk-aaaaaaaaaaaaaaaaaaaaaaaa")
    widget_b = _widget("tenant-b", "wk-bbbbbbbbbbbbbbbbbbbbbbbb")
    bundle_a = issue_session_authority(widget=widget_a)
    bundle_b = issue_session_authority(widget=widget_b)
    web_store.get_or_create_visitor(
        session_id=bundle_a.session_id,
        widget=widget_a,
        greeting="A",
        authority_hash=bundle_a.authority_hash,
    )
    web_store.get_or_create_visitor(
        session_id=bundle_b.session_id,
        widget=widget_b,
        greeting="B",
        authority_hash=bundle_b.authority_hash,
    )
    web_store.queue_assistant_message(bundle_a.session_id, "Only A", idempotency_key="a1")

    with pytest.raises(SessionAuthorityError):
        poll_pending_messages(
            session_id=bundle_a.session_id,
            widget=widget_b,
            session_authority=bundle_a.authority_token,
            store=web_store,
        )

    out = poll_pending_messages(
        session_id=bundle_a.session_id,
        widget=widget_a,
        session_authority=bundle_a.authority_token,
        store=web_store,
    )
    assert out["messages"][0]["content"] == "Only A"
    out_b = poll_pending_messages(
        session_id=bundle_b.session_id,
        widget=widget_b,
        session_authority=bundle_b.authority_token,
        store=web_store,
    )
    assert out_b["messages"] == []


def test_migration_path_rejects_legacy_session_without_authority(web_store, ha_db, monkeypatch) -> None:
    monkeypatch.delenv("WEB_CHAT_ALLOW_FILE_STORE", raising=False)
    widget = _widget()
    web_store.get_or_create_visitor(session_id="legacy-no-auth", widget=widget, greeting="Hi", authority_hash="")
    with pytest.raises(SessionAuthorityError) as exc:
        poll_pending_messages(
            session_id="legacy-no-auth",
            widget=widget,
            session_authority="any-token",
            store=web_store,
        )
    assert exc.value.code == "LEGACY_SESSION_REJECTED"


@pytest.mark.asyncio
async def test_crash_boundary_persist_without_queue_leaves_no_pending(web_chat_pg_store, monkeypatch) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    from db.models.whatsapp_smart_followup import WhatsAppSmartFollowUpJob
    from services.smart_followup.adapters.web import WebFollowUpAdapter
    from services.smart_followup.types import FollowUpConversationView

    store = web_chat_pg_store
    widget = seed_widget_config(store, _widget())
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    store.get_or_create_visitor(
        session_id="visitor-crash",
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    save_mock = AsyncMock(
        return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
            outcome="created",
            conversation_id=f"web:{widget.tenant_id}:visitor-crash",
        )
    )
    monkeypatch.setattr("services.web_chat.followup_delivery.persist_web_chat_message", save_mock)
    monkeypatch.setattr(
        store,
        "queue_assistant_message",
        MagicMock(side_effect=RuntimeError("crash before queue")),
    )

    job = WhatsAppSmartFollowUpJob(
        tenant_id=widget.tenant_id,
        channel="web_chat",
        connection_id=widget.widget_key,
        conversation_id=f"web:{widget.tenant_id}:visitor-crash",
        channel_context={},
        sequence_id="seq-1",
        step_index=1,
        goal="gentle_check_in",
        delay_minutes=30,
        due_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        control_epoch=1,
        idempotency_key="sfu:crash:2",
    )
    conv = FollowUpConversationView(
        channel="web_chat",
        tenant_id=widget.tenant_id,
        conversation_id=f"web:{widget.tenant_id}:visitor-crash",
        connection_id=widget.widget_key,
        control_epoch=1,
        control_state="AI_ACTIVE",
        service_window_opens_at=None,
        last_inbound_at=None,
        social_sender_id="visitor-crash",
    )
    result = await WebFollowUpAdapter().send_followup(
        session=MagicMock(),
        job=job,
        conv=conv,
        reply_text="Checking in",
        idempotency_key="sfu:crash:2",
    )
    assert result.status == "failed"
    session = store.get_visitor("visitor-crash")
    assert session is not None
    assert len(session.pending_assistant) == 0


def test_acceptance_ha_poll_requires_authority_hash(web_store, ha_db, monkeypatch) -> None:
    """Acceptance: HA-required mode rejects legacy sessions without authority."""
    monkeypatch.delenv("WEB_CHAT_ALLOW_FILE_STORE", raising=False)
    widget = _widget()
    web_store.get_or_create_visitor(session_id="legacy-acceptance", widget=widget, greeting="Hi", authority_hash="")
    with pytest.raises(SessionAuthorityError) as exc:
        poll_pending_messages(
            session_id="legacy-acceptance",
            widget=widget,
            session_authority="token",
            store=web_store,
        )
    assert exc.value.code == "LEGACY_SESSION_REJECTED"
