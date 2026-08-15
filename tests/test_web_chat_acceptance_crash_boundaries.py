"""Kill/restart crash boundaries: CAPTURED resume and COMPLETE turn repair."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.web_chat.operation import try_advance_operation
from services.web_chat.operation_fsm import OperationState, stable_operation_key
from services.web_chat.processor import WebChatError, process_web_chat_message
from services.web_chat.store_pg import WebChatPgStore
from tests.test_web_chat_acceptance_fsm import _widget_and_visitor
from tests.test_web_chat_operation_lease_fence import _expire_operation_lease
from tests.web_chat_acceptance_billing import assert_acceptance_ledger_equation, fetch_pg_ledger_snapshot
from tests.web_chat_acceptance_support import patch_acceptance_eligibility, patch_ai_reply, patch_web_chat_store
from tests.web_chat_runtime_support import count_messages_by_role, fetch_ha_side_effect_counts


def _operation_state(postgres_url: str, *, tenant_id: str, operation_key: str) -> str:
    from sqlalchemy import create_engine, text

    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT state FROM web_chat_operations WHERE tenant_id = :tid AND operation_key = :key"),
            {"tid": tenant_id, "key": operation_key},
        ).fetchone()
    assert row is not None
    return str(row[0])


def _delete_turn_messages(postgres_url: str, *, session_id: str, operation_key: str) -> None:
    from sqlalchemy import create_engine, text

    engine = create_engine(postgres_url, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM web_chat_messages WHERE session_id = :sid AND message_id LIKE :prefix"),
            {"sid": session_id, "prefix": f"{operation_key}:%"},
        )


@pytest.mark.asyncio
async def test_captured_before_complete_restart_no_second_ai(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Crash after CAPTURED must resume from canonical result with zero new AI calls."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    idempotency_key = "crash-captured-before-complete"
    operation_key = stable_operation_key(session_id=bundle.session_id, client_key=idempotency_key)

    ai_calls = 0

    async def counted_ai(*_args, **_kwargs):
        nonlocal ai_calls
        ai_calls += 1
        return MagicMock(reply="Acceptance AI reply")

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=counted_ai),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            side_effect=lambda **_kwargs: __import__(
                "services.web_chat.persistence", fromlist=["PersistResult", "PersistOutcome"]
            ).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=f"web:{widget.tenant_id}:{bundle.session_id}",
            )
        ),
    )

    original_advance = try_advance_operation
    complete_attempts = 0

    def kill_before_complete(runtime, from_state, target, **kwargs):
        nonlocal complete_attempts
        if from_state == OperationState.CAPTURED and target == OperationState.COMPLETE:
            complete_attempts += 1
            if complete_attempts == 1:
                raise RuntimeError("kill after captured before complete")
        return original_advance(runtime, from_state, target, **kwargs)

    monkeypatch.setattr("services.web_chat.processor_turn_finalize.try_advance_operation", kill_before_complete)
    monkeypatch.setattr("services.web_chat.processor_completion.try_advance_operation", kill_before_complete)

    with pytest.raises(RuntimeError, match="kill after captured before complete"):
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Crash boundary A",
            store=store,
            idempotency_key=idempotency_key,
        )

    assert ai_calls == 1
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.CAPTURED.value
    )

    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Crash boundary A",
        store=store,
        idempotency_key=idempotency_key,
    )
    assert reply == "Acceptance AI reply"
    assert ai_calls == 1
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.COMPLETE.value
    )

    counts = fetch_ha_side_effect_counts(acceptance_pg_ha_env, session_id=bundle.session_id)
    assert counts.assistant_messages == 2  # greeting + one canonical turn
    assert count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="assistant") == 2

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert snapshot.ops.get("capture", 0) == 1
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "reserve": 1, "capture": 1},
        captured=1,
    )


@pytest.mark.asyncio
async def test_complete_replay_repairs_missing_turn(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """COMPLETE without a durable PG turn must repair the transcript before any early return."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    idempotency_key = "crash-complete-without-turn"
    operation_key = stable_operation_key(session_id=bundle.session_id, client_key=idempotency_key)
    canonical_reply = "Canonical stored reply"

    patch_ai_reply(monkeypatch, reply=canonical_reply)
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            side_effect=lambda **_kwargs: __import__(
                "services.web_chat.persistence", fromlist=["PersistResult", "PersistOutcome"]
            ).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=f"web:{widget.tenant_id}:{bundle.session_id}",
            )
        ),
    )

    await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Crash boundary B",
        store=store,
        idempotency_key=idempotency_key,
    )
    _delete_turn_messages(acceptance_pg_ha_env, session_id=bundle.session_id, operation_key=operation_key)

    before = count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="assistant")
    assert before == 1  # greeting only

    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Crash boundary B",
        store=store,
        idempotency_key=idempotency_key,
    )
    assert reply == canonical_reply
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.COMPLETE.value
    )

    after = count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="assistant")
    assert after == 2
    refreshed = store.get_visitor(bundle.session_id)
    assert refreshed is not None
    assistant_turns = [m.content for m in refreshed.messages if m.role == "assistant" and m.content == canonical_reply]
    assert len(assistant_turns) == 1


@pytest.mark.asyncio
async def test_append_before_complete_crash_retries_to_one_turn(tmp_path, monkeypatch, acceptance_pg_ha_env) -> None:
    """Crash after canonical append but before COMPLETE commit must converge to one durable turn."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    idempotency_key = "crash-append-before-complete"
    patch_ai_reply(monkeypatch)

    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            side_effect=lambda **_kwargs: __import__(
                "services.web_chat.persistence", fromlist=["PersistResult", "PersistOutcome"]
            ).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=f"web:{widget.tenant_id}:{bundle.session_id}",
            )
        ),
    )

    original_advance = try_advance_operation
    complete_attempts = 0

    def kill_on_first_complete(runtime, from_state, target, **kwargs):
        nonlocal complete_attempts
        if from_state == OperationState.CAPTURED and target == OperationState.COMPLETE:
            complete_attempts += 1
            if complete_attempts == 1:
                raise RuntimeError("kill after append before complete commit")
        return original_advance(runtime, from_state, target, **kwargs)

    monkeypatch.setattr("services.web_chat.processor_turn_finalize.try_advance_operation", kill_on_first_complete)
    monkeypatch.setattr("services.web_chat.processor_completion.try_advance_operation", kill_on_first_complete)

    with pytest.raises(RuntimeError, match="kill after append before complete commit"):
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Crash boundary B2",
            store=store,
            idempotency_key=idempotency_key,
        )

    # Turn append happens before COMPLETE; operation stays CAPTURED after failed advance.
    operation_key = stable_operation_key(session_id=bundle.session_id, client_key=idempotency_key)
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.CAPTURED.value
    )
    mid = count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="assistant")
    assert mid == 2

    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Crash boundary B2",
        store=store,
        idempotency_key=idempotency_key,
    )
    assert reply == "Acceptance AI reply"
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.COMPLETE.value
    )
    final = count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="assistant")
    assert final == 2


@pytest.mark.asyncio
async def test_captured_active_lease_blocks_retry_until_expiry_then_resumes(
    tmp_path, monkeypatch, acceptance_pg_ha_env
) -> None:
    """Hard crash leaves CAPTURED lease held; retry waits for TTL expiry, then completes without re-AI."""
    monkeypatch.setenv("WEB_CHAT_PUBLIC_AVAILABILITY", "true")
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    store = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store)
    widget, visitor, bundle = _widget_and_visitor(store)
    idempotency_key = "crash-captured-lease-ttl"
    operation_key = stable_operation_key(session_id=bundle.session_id, client_key=idempotency_key)

    ai_calls = 0

    async def counted_ai(*_args, **_kwargs):
        nonlocal ai_calls
        ai_calls += 1
        return MagicMock(reply="Acceptance AI reply")

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(side_effect=counted_ai),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            side_effect=lambda **_kwargs: __import__(
                "services.web_chat.persistence", fromlist=["PersistResult", "PersistOutcome"]
            ).PersistResult(
                outcome=__import__("services.web_chat.persistence", fromlist=["PersistOutcome"]).PersistOutcome.CREATED,
                conversation_id=f"web:{widget.tenant_id}:{bundle.session_id}",
            )
        ),
    )

    original_advance = try_advance_operation
    complete_attempts = 0

    def kill_before_complete(runtime, from_state, target, **kwargs):
        nonlocal complete_attempts
        if from_state == OperationState.CAPTURED and target == OperationState.COMPLETE:
            complete_attempts += 1
            if complete_attempts == 1:
                raise RuntimeError("hard crash before complete commit")
        return original_advance(runtime, from_state, target, **kwargs)

    monkeypatch.setattr("services.web_chat.processor_turn_finalize.try_advance_operation", kill_before_complete)
    monkeypatch.setattr("services.web_chat.processor_completion.try_advance_operation", kill_before_complete)

    original_abandon = __import__(
        "services.web_chat.processor_turn_finalize", fromlist=["abandon_operation_lease"]
    ).abandon_operation_lease
    abandon_calls = 0

    def skip_first_abandon(runtime):
        nonlocal abandon_calls
        abandon_calls += 1
        if abandon_calls == 1:
            return
        original_abandon(runtime)

    monkeypatch.setattr("services.web_chat.processor_turn_finalize.abandon_operation_lease", skip_first_abandon)

    with pytest.raises(RuntimeError, match="hard crash before complete commit"):
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Crash boundary TTL",
            store=store,
            idempotency_key=idempotency_key,
        )

    assert ai_calls == 1
    assert abandon_calls == 1
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.CAPTURED.value
    )

    with pytest.raises(WebChatError) as blocked:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Crash boundary TTL",
            store=store,
            idempotency_key=idempotency_key,
        )
    assert blocked.value.code == "operation_in_progress"
    assert ai_calls == 1

    _expire_operation_lease(tenant_id=widget.tenant_id, operation_key=operation_key)

    reply = await process_web_chat_message(
        widget=widget,
        visitor_session=visitor,
        user_text="Crash boundary TTL",
        store=store,
        idempotency_key=idempotency_key,
    )
    assert reply == "Acceptance AI reply"
    assert ai_calls == 1
    assert _operation_state(acceptance_pg_ha_env, tenant_id=widget.tenant_id, operation_key=operation_key) == (
        OperationState.COMPLETE.value
    )

    counts = fetch_ha_side_effect_counts(acceptance_pg_ha_env, session_id=bundle.session_id)
    assert counts.assistant_messages == 2
    assert count_messages_by_role(acceptance_pg_ha_env, session_id=bundle.session_id, role="assistant") == 2

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, widget.tenant_id)
    assert snapshot.ops.get("capture", 0) == 1
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"grant_included": 1, "reserve": 1, "capture": 1},
        captured=1,
    )
