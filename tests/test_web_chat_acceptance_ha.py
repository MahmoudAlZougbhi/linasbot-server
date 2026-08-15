"""HA acceptance: shared PostgreSQL, disjoint roots, dual-process restart simulation."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from db.session import reset_engine_for_tests
from services.web_chat.delivery_outbox import ack_pending_messages, poll_pending_messages
from services.web_chat.ha_repository import WebChatHaRepository
from services.web_chat.processor import process_web_chat_message
from services.web_chat.session_authority import issue_session_authority
from services.web_chat.store_pg import WebChatPgStore
from tests.web_chat_acceptance_billing import (
    assert_acceptance_ledger_equation,
    fetch_pg_ledger_snapshot,
)
from tests.web_chat_acceptance_support import (
    patch_acceptance_eligibility,
    patch_web_chat_store,
    seed_acceptance_widget,
    seed_prefix_widget_pair,
)
from tests.web_chat_runtime_support import (
    http_ack_session,
    http_poll_session,
    http_post_json_response,
    spawn_web_chat_server,
    stop_web_chat_server,
)


def test_two_nodes_disjoint_roots_share_ha_poll_ack(monkeypatch, acceptance_pg_ha_env, tmp_path) -> None:
    """Two independent uvicorn processes, disjoint local roots, one PostgreSQL HA store."""
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    root_a = tmp_path / "node-a"
    root_b = tmp_path / "node-b"
    seed_store = WebChatPgStore()
    widget_key, tenant_id = seed_acceptance_widget(seed_store)
    widget = seed_store.get_widget_by_key(widget_key)
    assert widget is not None
    bundle = issue_session_authority(widget=widget)
    seed_store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    seed_store.queue_assistant_message(
        bundle.session_id,
        "HA follow-up",
        idempotency_key="sfu:ha:1",
    )

    server_a = spawn_web_chat_server(postgres_url=acceptance_pg_ha_env, data_root=root_a)
    server_b = spawn_web_chat_server(postgres_url=acceptance_pg_ha_env, data_root=root_b)
    try:
        assert server_a.data_root != server_b.data_root
        assert server_a.port != server_b.port

        polled_b = http_poll_session(
            server_b.base_url,
            widget_key=widget_key,
            session_id=bundle.session_id,
            session_authority=bundle.authority_token,
        )
        assert polled_b["messages"][0]["content"] == "HA follow-up"

        acked_a = http_ack_session(
            server_a.base_url,
            widget_key=widget_key,
            session_id=bundle.session_id,
            session_authority=bundle.authority_token,
            message_ids=["sfu:ha:1"],
        )
        assert acked_a["acked"] == 1

        again = http_poll_session(
            server_b.base_url,
            widget_key=widget_key,
            session_id=bundle.session_id,
            session_authority=bundle.authority_token,
            cursor=polled_b.get("cursor"),
        )
        assert again["messages"] == []
    finally:
        stop_web_chat_server(server_a)
        stop_web_chat_server(server_b)

    snapshot = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert_acceptance_ledger_equation(
        snapshot,
        start_total=start_total,
        expected_available=start_total,
        expected_reserved=0,
        expected_ops={"grant_included": 1},
    )


def test_two_nodes_adversarial_cross_tenant_poll_ack_rejected(monkeypatch, acceptance_pg_ha_env, tmp_path) -> None:
    """Real HTTP on two processes: stolen session_id/authority rejected; ledgers unchanged."""
    from tests.web_chat_acceptance_billing import seed_acceptance_credit_ledger

    start_a = patch_acceptance_eligibility(monkeypatch, tmp_path, tenant_id="biz-a")
    start_b = seed_acceptance_credit_ledger(tenant_id="biz-b")
    root_a = tmp_path / "adv-node-a"
    root_b = tmp_path / "adv-node-b"
    seed_store = WebChatPgStore()
    key_a, key_b = seed_prefix_widget_pair(seed_store)
    widget_a = seed_store.get_widget_by_key(key_a)
    widget_b = seed_store.get_widget_by_key(key_b)
    assert widget_a is not None and widget_b is not None

    bundle_a = issue_session_authority(widget=widget_a)
    seed_store.get_or_create_visitor(
        session_id=bundle_a.session_id,
        widget=widget_a,
        greeting="Hi",
        authority_hash=bundle_a.authority_hash,
    )
    seed_store.queue_assistant_message(
        bundle_a.session_id,
        "Tenant-A secret",
        idempotency_key="sfu:adv:1",
    )

    server_a = spawn_web_chat_server(postgres_url=acceptance_pg_ha_env, data_root=root_a)
    server_b = spawn_web_chat_server(postgres_url=acceptance_pg_ha_env, data_root=root_b)
    try:
        poll_status, poll_body = http_post_json_response(
            server_b.base_url,
            "/api/web-chat/session/poll",
            {
                "session_id": bundle_a.session_id,
                "session_authority": bundle_a.authority_token,
                "widget_key": key_b,
                "cursor": None,
            },
        )
        assert poll_status == 403
        assert poll_body.get("error") == "SESSION_BOUNDARY"

        ack_status, ack_body = http_post_json_response(
            server_a.base_url,
            "/api/web-chat/session/ack",
            {
                "session_id": bundle_a.session_id,
                "session_authority": bundle_a.authority_token,
                "widget_key": key_b,
                "message_ids": ["sfu:adv:1"],
            },
        )
        assert ack_status == 403
        assert ack_body.get("error") == "SESSION_BOUNDARY"

        legit = http_poll_session(
            server_a.base_url,
            widget_key=key_a,
            session_id=bundle_a.session_id,
            session_authority=bundle_a.authority_token,
        )
        assert legit["messages"][0]["content"] == "Tenant-A secret"
    finally:
        stop_web_chat_server(server_a)
        stop_web_chat_server(server_b)

    snap_a = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz-a")
    snap_b = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, "biz-b")
    assert_acceptance_ledger_equation(
        snap_a,
        start_total=start_a,
        expected_available=start_a,
        expected_reserved=0,
        expected_ops={"grant_included": 1},
    )
    assert_acceptance_ledger_equation(
        snap_b,
        start_total=start_b,
        expected_available=start_b,
        expected_reserved=0,
        expected_ops={"grant_included": 1},
    )


def test_restart_simulation_new_process_reads_ha_pending(monkeypatch, acceptance_pg_ha_env, tmp_path) -> None:
    """Kill/recreate uvicorn; HA outbox + PG credit rows survive in shared PostgreSQL."""
    start_total = patch_acceptance_eligibility(monkeypatch, tmp_path)
    root_v1 = tmp_path / "restart-v1"
    root_v2 = tmp_path / "restart-v2"
    seed_store = WebChatPgStore()
    widget_key, tenant_id = seed_acceptance_widget(seed_store)
    widget = seed_store.get_widget_by_key(widget_key)
    assert widget is not None
    bundle = issue_session_authority(widget=widget)
    visitor = seed_store.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )

    monkeypatch.setattr(
        "services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm",
        AsyncMock(return_value=MagicMock(reply="Captured before restart")),
    )
    monkeypatch.setattr(
        "services.web_chat.processor.persist_web_chat_message",
        AsyncMock(
            return_value=__import__("services.web_chat.persistence", fromlist=["PersistResult"]).PersistResult(
                outcome="created",
                conversation_id=f"web:{tenant_id}:{bundle.session_id}",
            )
        ),
    )

    async def _capture_credit_before_restart() -> None:
        await process_web_chat_message(
            widget=widget,
            visitor_session=visitor,
            user_text="Pre-restart inbound",
            store=seed_store,
            idempotency_key="client-key-restart",
        )

    asyncio.run(_capture_credit_before_restart())

    after_capture = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert after_capture.ops.get("reserve", 0) == 1
    assert after_capture.ops.get("capture", 0) == 1
    assert_acceptance_ledger_equation(
        after_capture,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "reserve": 1},
        captured=1,
    )

    seed_store.queue_assistant_message(
        bundle.session_id,
        "Survives restart",
        idempotency_key="sfu:restart:1",
    )

    server_v1 = spawn_web_chat_server(postgres_url=acceptance_pg_ha_env, data_root=root_v1)
    try:
        warm = http_poll_session(
            server_v1.base_url,
            widget_key=widget_key,
            session_id=bundle.session_id,
            session_authority=bundle.authority_token,
        )
        assert warm["messages"][0]["id"] == "sfu:restart:1"
    finally:
        stop_web_chat_server(server_v1)

    reset_engine_for_tests()
    server_v2 = spawn_web_chat_server(postgres_url=acceptance_pg_ha_env, data_root=root_v2)
    try:
        out = http_poll_session(
            server_v2.base_url,
            widget_key=widget_key,
            session_id=bundle.session_id,
            session_authority=bundle.authority_token,
        )
        assert len(out["messages"]) == 1
        assert out["messages"][0]["id"] == "sfu:restart:1"
        assert server_v2.data_root != root_v1
    finally:
        stop_web_chat_server(server_v2)
        reset_engine_for_tests()

    after_restart = fetch_pg_ledger_snapshot(acceptance_pg_ha_env, tenant_id)
    assert after_restart == after_capture
    assert_acceptance_ledger_equation(
        after_restart,
        start_total=start_total,
        expected_available=start_total - 1,
        expected_reserved=0,
        expected_ops={"capture": 1, "grant_included": 1, "reserve": 1},
        captured=1,
    )


def test_in_process_store_poll_ack_still_valid(monkeypatch, acceptance_pg_ha_env, tmp_path) -> None:
    """Supplementary in-process poll/ack path (not a substitute for dual-process HA)."""
    root_a = tmp_path / "node-a-local"
    root_b = tmp_path / "node-b-local"
    root_a.mkdir()
    root_b.mkdir()
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(root_a))

    store_a = WebChatPgStore()
    store_b = WebChatPgStore()
    patch_web_chat_store(monkeypatch, store_a)

    widget_key, _tenant_id = seed_acceptance_widget(store_a)
    widget = store_a.get_widget_by_key(widget_key)
    assert widget is not None
    bundle = issue_session_authority(widget=widget)
    store_a.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    store_b.get_or_create_visitor(
        session_id=bundle.session_id,
        widget=widget,
        greeting="Hi",
        authority_hash=bundle.authority_hash,
    )
    store_a.queue_assistant_message(
        bundle.session_id,
        "HA follow-up",
        idempotency_key="sfu:ha:local:1",
    )

    polled_b = poll_pending_messages(
        session_id=bundle.session_id,
        widget=widget,
        session_authority=bundle.authority_token,
        store=store_b,
    )
    assert polled_b["messages"][0]["content"] == "HA follow-up"

    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(root_b))
    acked_a = ack_pending_messages(
        session_id=bundle.session_id,
        widget=widget,
        session_authority=bundle.authority_token,
        message_ids=["sfu:ha:local:1"],
        store=store_a,
    )
    assert acked_a["acked"] == 1

    again = poll_pending_messages(
        session_id=bundle.session_id,
        widget=widget,
        session_authority=bundle.authority_token,
        store=store_b,
    )
    assert again["messages"] == []


def test_ha_idempotency_row_visible_after_queue(web_chat_ha_db) -> None:
    from services.web_chat.pg_models import WebChatDeliveryIdempotencyRow

    repo = WebChatHaRepository()
    with web_chat_ha_db() as db:
        repo.create_session(
            db,
            session_id="visitor-idem-acc",
            tenant_id="biz",
            widget_key="wk-idem",
            authority_hash="hash",
            greeting="Hi",
        )
        claimed = repo.claim_idempotency(
            db,
            tenant_id="biz",
            session_id="visitor-idem-acc",
            idempotency_key="sfu:idem:acc",
            message_id="sfu:idem:acc",
        )
        db.commit()
    assert claimed is True
    with web_chat_ha_db() as db:
        row = db.scalars(
            select(WebChatDeliveryIdempotencyRow).where(WebChatDeliveryIdempotencyRow.idempotency_key == "sfu:idem:acc")
        ).first()
        assert row is not None
        assert row.message_id == "sfu:idem:acc"


def test_schema_absence_raises_when_db_unconfigured(monkeypatch) -> None:
    from services.web_chat.ha_repository import WebChatHaUnavailable, with_ha_session

    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    reset_engine_for_tests()
    with pytest.raises(WebChatHaUnavailable):
        with with_ha_session():
            pass
    reset_engine_for_tests()
