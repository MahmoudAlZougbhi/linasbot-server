"""Safety writes stay available after the daily AI Setup limit."""

from __future__ import annotations

import pytest

from services.membership.daily_edits import (
    DailyEditLimitError,
    commit_edit,
    reserve_edit,
    reset_daily_edits_for_tests,
    set_platform_baseline,
)
from services.membership.edit_http import guarded_edit, is_safety_edit


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_daily_edits_for_tests()


def test_ai_limits_section_consumes_daily_edit() -> None:
    from services.membership.daily_edits import COUNTED_CM_SECTIONS

    assert "ai_limits" in COUNTED_CM_SECTIONS


def test_unpublish_and_archive_are_safety_kinds() -> None:
    assert is_safety_edit("cm:unpublish") is True
    assert is_safety_edit("faq:archive") is True
    assert is_safety_edit("safety:disconnect") is True
    assert is_safety_edit("safety:handoff") is True
    assert is_safety_edit("safety:ai-disable") is True
    assert is_safety_edit("safety:web-chat-disable") is True
    assert is_safety_edit("safety:toggle:instagram:dm") is True
    assert is_safety_edit("privacy:delete") is True
    assert is_safety_edit("safety:webhook") is True
    assert is_safety_edit("cm:publish:all") is False
    assert is_safety_edit("faq:patch") is False
    assert is_safety_edit("whatsapp:ai-enable") is False
    assert is_safety_edit("web-chat:settings") is False
    assert is_safety_edit("integration:toggle:instagram:dm") is False


def test_safety_edits_work_when_daily_limit_is_zero() -> None:
    set_platform_baseline(0)
    with pytest.raises(DailyEditLimitError):
        with guarded_edit(tenant_id="safe-shop", kind="cm:publish:all", payload={"notes": "x"}):
            raise AssertionError("ordinary publish must stay blocked")
    with guarded_edit(tenant_id="safe-shop", kind="cm:unpublish", payload={"previous": "v1"}):
        pass
    with guarded_edit(tenant_id="safe-shop", kind="faq:archive", payload={"id": "faq-1"}, safety=True):
        pass
    with guarded_edit(tenant_id="safe-shop", kind="safety:disconnect", payload={"platform": "instagram"}):
        pass


def test_web_chat_keeps_single_reservation_lifecycle() -> None:
    from inspect import getsource

    from services.omnichannel import generate as omni_generate
    from services.web_chat import processor_completion

    assert "reserve_leftover_reply" not in getsource(processor_completion)
    assert "reserve_leftover_reply" in getsource(omni_generate)


def test_comment_replies_and_request_preview_consume_daily_edits() -> None:
    from inspect import getsource

    from modules import cm_request_graphs_api, meta_connections_api_lifecycle

    src = getsource(meta_connections_api_lifecycle.update_meta_comment_replies)
    assert "integration:comment-replies" in src
    assert "safety:toggle:comment-replies" in src
    assert "request-graph:preview" in getsource(cm_request_graphs_api.request_graph_preview)


def test_channel_setup_writes_consume_or_skip_daily_edits() -> None:
    from inspect import getsource

    from modules import mobile_integrations_api, web_chat_mobile_routes, whatsapp_cloud_ops_api

    toggles = getsource(mobile_integrations_api.mobile_integration_toggles)
    assert "integration:toggle:" in toggles
    assert "safety:toggle:" in toggles
    web = getsource(web_chat_mobile_routes.mobile_web_chat_update)
    assert "web-chat:settings" in web
    assert "safety:web-chat-disable" in web
    assert "safety:web-chat-rotate" in getsource(web_chat_mobile_routes.mobile_web_chat_rotate_key)
    assert "whatsapp:ai-enable" in getsource(whatsapp_cloud_ops_api.whatsapp_enable_ai)
    assert "safety:ai-disable" in getsource(whatsapp_cloud_ops_api.whatsapp_disable_ai)


def test_disconnect_routes_use_safety_edit() -> None:
    from inspect import getsource

    from modules import mobile_integrations_api, tiktok_business_api, whatsapp_cloud_ops_api

    assert "safety:disconnect" in getsource(mobile_integrations_api.mobile_disconnect_platform)
    assert "safety:disconnect" in getsource(tiktok_business_api.tiktok_disconnect)
    assert "safety:disconnect" in getsource(whatsapp_cloud_ops_api.whatsapp_disconnect)
    from modules import live_chat_api

    assert "safety:handoff" in getsource(live_chat_api.takeover_conversation)
    assert "safety:handoff" in getsource(live_chat_api.release_conversation)
    assert "safety:handoff" in getsource(live_chat_api.end_conversation)
    from modules import meta_connections_api_recovery, mobile_integrations_api

    assert "safety:webhook" in getsource(mobile_integrations_api.mobile_reconcile_comments)
    assert "safety:webhook" in getsource(meta_connections_api_recovery.retry_instagram_login_webhook_setup)
    from modules import meta_connections_api_lifecycle as meta_lifecycle

    assert "safety:rollback" in getsource(meta_lifecycle.rollback_meta_connection)


def test_account_delete_is_privacy_safety_edit() -> None:
    from inspect import getsource

    from modules import apple_auth_api, auth_users_api

    apple = getsource(apple_auth_api.mobile_account_delete)
    assert "privacy:delete" in apple
    assert "safety=True" in apple
    admin = getsource(auth_users_api.delete_user)
    assert "privacy:delete" in admin
    assert "safety=True" in admin


def test_social_processor_stays_under_line_cap_and_finalizes_delivery() -> None:
    from inspect import getsource
    from pathlib import Path

    from services.social_messaging_processor import (
        meta_social_outcome_requires_retry,
        process_meta_social_event,
    )
    from services.social_turn_outcome import finalize_social_turn

    processor = Path("services/social_messaging_processor.py").read_text(encoding="utf-8")
    assert processor.count("\n") <= 500
    assert "finalize_social_turn" in getsource(process_meta_social_event)
    assert "finalize_delivery" in getsource(finalize_social_turn)
    assert meta_social_outcome_requires_retry({"delivery": "delivered"}) is False
    assert meta_social_outcome_requires_retry({"delivery": "unknown"}) is True


def test_missing_daily_edit_tables_fall_back_to_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.daily_edits_pg.table_ready", lambda _s: False)
    monkeypatch.setattr("services.membership.daily_edits_policy_pg.table_ready", lambda _s: False)
    set_platform_baseline(1)
    reserve_edit(tenant_id="fallback-shop", operation_id="op-1")
    commit_edit(tenant_id="fallback-shop", operation_id="op-1")
    with pytest.raises(DailyEditLimitError):
        reserve_edit(tenant_id="fallback-shop", operation_id="op-2")


def test_daily_edit_status_unions_memory_when_sql_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.daily_edits import status

    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    set_platform_baseline(1)
    reserve_edit(tenant_id="mix-shop", operation_id="op-mem")
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.daily_edits_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.daily_edits_pg.pg_counts", lambda *_a, **_k: (0, 0))
    monkeypatch.setattr("services.membership.daily_edits_pg.pg_operation_ids", lambda *_a, **_k: {})
    state = status("mix-shop")
    assert state.reserved == 1
    assert state.remaining == 0
    with pytest.raises(DailyEditLimitError):
        reserve_edit(tenant_id="mix-shop", operation_id="op-new")


def test_known_processing_tenants_union_memory_and_sql(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.processing_budgets import (
        begin_job,
        known_processing_tenant_ids,
        reset_processing_budgets_for_tests,
    )

    reset_processing_budgets_for_tests()
    begin_job("mem-budget")
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.processing_budgets_pg.table_ready", lambda _s: True)
    monkeypatch.setattr(
        "services.membership.processing_budgets_pg.pg_tenant_ids",
        lambda _s: ["sql-budget"],
    )
    assert known_processing_tenant_ids() == ["mem-budget", "sql-budget"]


def test_processing_status_unions_memory_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.processing_budgets import (
        ProcessingBudgetError,
        begin_job,
        reset_processing_budgets_for_tests,
        status,
    )

    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_processing_budgets_for_tests()
    begin_job("mem-stat")
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.processing_budgets_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.processing_budgets_pg.pg_job_count", lambda *_a, **_k: 1)
    monkeypatch.setattr("services.membership.processing_budgets_pg.pg_attempt_used", lambda *_a, **_k: 2)
    monkeypatch.setattr("services.membership.processing_budgets_pg.pg_tenants_with_jobs", lambda *_a, **_k: 1)
    state = status("mem-stat")
    assert state["concurrent"] == 2
    assert state["daily_attempts"] == 2
    with pytest.raises(ProcessingBudgetError):
        begin_job("mem-stat")


def test_expense_list_unions_memory_when_sql_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.expense_journal import list_events, record_expense, reset_expenses_for_tests

    reset_expenses_for_tests()
    record_expense(
        event_id="mem-exp",
        tenant_id="mem-exp-shop",
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model="gpt-test",
        amount_usd="0.01",
    )
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.expense_journal_pg.table_ready", lambda _s: True)
    monkeypatch.setattr("services.membership.expense_journal_pg.pg_list", lambda *_a, **_k: [])
    events = list_events(tenant_id="mem-exp-shop")
    assert any(item.event_id == "mem-exp" for item in events)


def test_end_job_without_local_id_does_not_close_sql_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    from services.membership.processing_budgets import end_job, reset_processing_budgets_for_tests

    reset_processing_budgets_for_tests()
    closed: list[tuple[str, str]] = []

    @contextmanager
    def _session():
        yield object()

    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.setattr("services.membership.pg_store.memory_forced", lambda: False)
    monkeypatch.setattr("services.membership.pg_store.optional_message_session", _session)
    monkeypatch.setattr("services.membership.processing_budgets_pg.table_ready", lambda _s: True)
    monkeypatch.setattr(
        "services.membership.processing_budgets_pg.pg_end_job",
        lambda _s, jid: closed.append(("job", jid)),
    )
    monkeypatch.setattr(
        "services.membership.processing_budgets_pg.pg_end_latest_job",
        lambda _s, tid: closed.append(("latest", tid)),
    )
    end_job("other-worker")
    assert closed == []
