"""FSM boundary fault injection and ledger equation acceptance tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.web_chat.credit_fsm import CreditFsmState, WebChatCreditHandle
from services.web_chat.followup_delivery import deliver_web_followup_message
from services.web_chat.processor import WebChatError, compose_web_user_id, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_followup_web_delivery import _reserve_followup_credit
from tests.web_chat_acceptance_billing import (
    assert_acceptance_ledger_equation,
    fetch_pg_ledger_snapshot,
)
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_ai_reply,
    patch_web_chat_store,
    seed_acceptance_widget,
)


def _widget_and_visitor(store: WebChatPgStore):
    from services.web_chat.session_authority import issue_session_authority

    widget_key, _tid = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    bundle = issue_session_authority(widget=widget)
    visitor = store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    return widget, visitor, bundle


@pytest.mark.asyncio
async def test_fsm_reserve_ai_failure_releases_credit(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)

    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=RuntimeError("ai down")),
    )

    with pytest.raises(WebChatError) as exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key="fsm-ai-fail",
        )
    assert exc.value.code == "ai_failed"
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "release": 1, "reserve": 1},
    )


@pytest.mark.asyncio
async def test_released_operation_same_client_key_retry_converges_without_integrity_error(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """Failure->release->same-key retry must reserve on a new attempt without IntegrityError."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)

    ai_calls = {"count": 0}

    async def ai_fail_then_succeed(**_kwargs):
        ai_calls["count"] += 1
        if ai_calls["count"] == 1:
            raise RuntimeError("ai down")
        from types import SimpleNamespace

        return SimpleNamespace(reply="Recovered reply")

    monkeypatch.setattr(
        "services.web_chat.processor.evaluate_web_ai_eligibility",
        lambda *_a, **_k: (True, None),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id="conv",
            )
        ),
    )
    monkeypatch.setattr("services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm", ai_fail_then_succeed)

    with pytest.raises(WebChatError) as exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key="released-retry-key",
        )
    assert exc.value.code == "ai_failed"
    after_fail = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert after_fail.reserved == 0
    assert after_fail.ops.get("release", 0) == 1
    assert after_fail.ops.get("reserve", 0) == 1

    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Hi",
        store=store,
        idempotency_key="released-retry-key",
    )
    assert reply == "Recovered reply"
    session = store.get_visitor(visitor.id)
    assert session is not None
    assert any(msg.role == "assistant" and msg.content == "Recovered reply" for msg in session.messages)

    final = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert_acceptance_ledger_equation(
        final,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "release": 1, "reserve": 2},
        captured=1,
    )


@pytest.mark.asyncio
async def test_fsm_capture_failure_enters_billing_pending(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)

    patch_ai_reply(monkeypatch, reply="AI")
    from services.credit_ledger_service import credit_ledger_service

    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id="conv",
            )
        ),
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
            user_text="Hi",
            store=store,
            idempotency_key="fsm-capture-fail",
        )
    assert exc.value.code == "credit_capture_failed"


@pytest.mark.asyncio
async def test_fsm_persist_failure_releases_credit(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, _bundle = _widget_and_visitor(store)

    patch_ai_reply(monkeypatch, reply="AI")
    from services.web_chat.persistence import PersistFailure

    monkeypatch.setattr(
        "services.web_chat.persistence.persist_web_chat_message",
        AsyncMock(side_effect=PersistFailure("firestore_error", "down")),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(side_effect=PersistFailure("firestore_error", "down")),
    )

    with pytest.raises(WebChatError) as exc:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Hi",
            store=store,
            idempotency_key="fsm-persist-fail",
        )
    assert exc.value.code == "persist_failed"
    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "release": 1, "reserve": 1},
    )


@pytest.mark.asyncio
async def test_fsm_followup_queue_failure_then_recovery(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget_key, tenant_id = seed_acceptance_widget(store)
    widget = store.get_widget_by_key(widget_key)
    assert widget is not None
    from services.web_chat.session_authority import issue_session_authority

    bundle = issue_session_authority(widget=widget)
    visitor_id = "visitor-fsm-queue"
    store.get_or_create_visitor(
        session_id=visitor_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    monkeypatch.setattr(
        "services.web_chat.persistence.persist_web_chat_message",
        AsyncMock(
            return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
                outcome="created",
                conversation_id=f"web:{tenant_id}:{visitor_id}",
            )
        ),
    )
    from services.web_chat.persistence import PersistOutcome, PersistResult

    monkeypatch.setattr(
        "services.web_chat.followup_delivery.persist_web_chat_message",
        AsyncMock(
            return_value=PersistResult(
                outcome=PersistOutcome.CREATED,
                conversation_id=f"web:{tenant_id}:{visitor_id}",
            )
        ),
    )
    attempts = 0
    original_queue = store.queue_assistant_message

    def queue_fail_once(session_id: str, content: str, *, idempotency_key: str | None = None) -> bool:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("queue/storage commit lost")
        return original_queue(session_id, content, idempotency_key=idempotency_key)

    monkeypatch.setattr(store, "queue_assistant_message", queue_fail_once)

    idem = "sfu:fsm:queue"
    reservation_id = _reserve_followup_credit(tenant_id=tenant_id, idem=idem)

    with pytest.raises(RuntimeError, match="queue/storage"):
        await deliver_web_followup_message(
            tenant_id=tenant_id,
            visitor_id=visitor_id,
            user_id=compose_web_user_id(visitor_id),
            conversation_id=f"web:{tenant_id}:{visitor_id}",
            reply_text="Recover me",
            idempotency_key=idem,
            widget_key=widget_key,
            authority_hash=bundle.authority_hash,
            store=store,
            reservation_id=reservation_id,
        )

    recovered = await deliver_web_followup_message(
        tenant_id=tenant_id,
        visitor_id=visitor_id,
        user_id=compose_web_user_id(visitor_id),
        conversation_id=f"web:{tenant_id}:{visitor_id}",
        reply_text="Recover me",
        idempotency_key=idem,
        widget_key=widget_key,
        authority_hash=bundle.authority_hash,
        store=store,
        reservation_id=reservation_id,
    )
    assert recovered.status in {"delivered", "already_delivered"}
    session = store.get_visitor(visitor_id)
    assert session is not None
    assert len(session.pending_assistant) == 1


def test_credit_handle_idle_reserve_capture_equation(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path, tenant_id="biz")
    from services.credit_ledger_service import credit_ledger_service

    handle = WebChatCreditHandle(tenant_id="biz", reservation_id=None, request_id="web:fsm:1")
    assert handle.state == CreditFsmState.IDLE
    handle.reserve()
    assert handle.state == CreditFsmState.RESERVED
    assert credit_ledger_service.get_reserved("biz") == 1
    reserved_snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz")
    assert_acceptance_ledger_equation(
        reserved_snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=1,
        expected_ops={"grant_included": 1, "reserve": 1},
    )

    handle.capture()
    assert handle.state == CreditFsmState.CAPTURED
    assert credit_ledger_service.get_reserved("biz") == 0
    assert credit_ledger_service.get_balance("biz") == start_total - 1
    captured_snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz")
    assert_acceptance_ledger_equation(
        captured_snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "reserve": 1},
        captured=1,
    )

    handle2 = WebChatCreditHandle(tenant_id="biz", reservation_id=None, request_id="web:fsm:2")
    handle2.reserve()
    handle2.release()
    assert handle2.state == CreditFsmState.RELEASED
    assert credit_ledger_service.get_balance("biz") == start_total - 1
    assert credit_ledger_service.get_reserved("biz") == 0
    final_snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz")
    assert_acceptance_ledger_equation(
        final_snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "release": 1, "reserve": 2},
        captured=1,
    )
