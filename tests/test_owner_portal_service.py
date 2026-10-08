from __future__ import annotations

from datetime import UTC, datetime

import pytest

import services.owner_copilot.interaction_flow_logger as flow_logger
import services.owner_portal.owner_portal_service as portal
from services.billing.membership.catalog_revenue import intended_price_usd
from services.billing.plan_economics import PLAN_PRICES_USD


def test_recent_flows_excludes_other_tenants_and_untagged_rows(monkeypatch):
    monkeypatch.setattr(flow_logger, "_INITIALIZED", True)
    flow_logger._FLOW_BUFFER.clear()
    flow_logger._FLOW_BUFFER.extend(
        [
            {"timestamp": "2026-08-17T08:00:00Z", "tenant_id": "alpha", "user_message": "a"},
            {"timestamp": "2026-08-17T08:01:00Z", "tenant_id": "beta", "user_message": "b"},
            {"timestamp": "2026-08-17T08:02:00Z", "tenant_id": None, "user_message": "legacy"},
        ]
    )

    rows = flow_logger.get_recent_flows(limit=50, tenant_id="alpha")

    assert [row["user_message"] for row in rows] == ["a"]


def test_billing_by_tenant_reads_columns_before_the_session_closes(monkeypatch):
    """Rows expire when the billing session exits. The copy must happen inside it."""

    class _Gate:
        closed = False

    gate = _Gate()

    class _Ent:
        tenant_id = "alpha"

        @property
        def plan_id(self):
            if gate.closed:
                raise RuntimeError("detached")
            return "growth"

        @property
        def status(self):
            if gate.closed:
                raise RuntimeError("detached")
            return "active"

        included_credits = 10
        extra_credits = 1

    class _Balance:
        @property
        def available(self):
            if gate.closed:
                raise RuntimeError("detached")
            return 4

    class _Session:
        def execute(self, _query):
            return self

        def all(self):
            return [(_Ent(), _Balance())]

    class _Ctx:
        def __enter__(self):
            return _Session()

        def __exit__(self, *_args):
            gate.closed = True
            return False

    monkeypatch.setattr(portal, "billing_uses_postgres", lambda: True)
    monkeypatch.setattr(portal, "require_billing_pg_session", lambda: _Ctx())

    loaded = portal._billing_by_tenant({"alpha"})

    assert loaded["alpha"]["plan_id"] == "growth"
    assert loaded["alpha"]["credits_remaining"] == 4
    assert gate.closed is True


def test_list_subscribers_groups_users_and_batches_billing(monkeypatch):
    users = [
        {"id": "u1", "tenantId": "alpha", "email": "owner@example.com", "role": "owner", "status": "active"},
        {"id": "u2", "tenantId": "alpha", "email": "staff@example.com", "role": "viewer", "status": "active"},
    ]
    monkeypatch.setattr(
        portal,
        "_billing_by_tenant",
        lambda tenant_ids: {
            "alpha": {
                "plan_id": "growth",
                "subscription_status": "active",
                "included_credits": 100,
                "extra_credits": 20,
                "credits_remaining": 75,
            }
        },
    )

    rows = portal.list_subscribers(users)

    assert rows[0]["seats_created"] == 2
    assert rows[0]["roles"] == ["owner", "viewer"]
    assert rows[0]["historical_credit_remaining"] == 75
    assert rows[0]["credits_remaining"] == rows[0]["message_remaining"]
    assert rows[0]["messages_remaining"] == rows[0]["message_remaining"]
    assert rows[0]["intended_included_messages"] == 3000
    assert rows[0]["intended_price_usd"] == 59.0


def test_daily_edit_zero_limit_blocks_reserve() -> None:
    from services.billing.membership.daily_edits import (
        DailyEditLimitError,
        reserve_edit,
        reset_daily_edits_for_tests,
        set_platform_baseline,
    )

    reset_daily_edits_for_tests()
    set_platform_baseline(0)
    try:
        try:
            reserve_edit(tenant_id="zero-edit", operation_id="op-1")
            raise AssertionError("zero limit must block")
        except DailyEditLimitError:
            pass
    finally:
        reset_daily_edits_for_tests()


def test_analytics_keeps_legacy_credits_and_adds_catalog_mrr(monkeypatch):
    monkeypatch.setattr(
        "services.owner_portal.flow_counts.channel_counts_for_range",
        lambda *_args, **_kwargs: {"messages_by_channel": {}, "comments": 0},
    )

    def _forbid(*_args, **_kwargs):
        raise AssertionError("analytics must not scan subscriber rows")

    monkeypatch.setattr(portal, "list_subscribers", _forbid)
    monkeypatch.setattr(
        "services.owner_portal.analytics_sql.load_overview",
        lambda *_args, **_kwargs: {
            "new_users": 0,
            "live_users": 0,
            "subscribers": 1,
            "credits_total": 7000,
            "credits_used": 10,
            "credits_remaining": 6990,
            "messages_total": 7000,
            "messages_used": 10,
            "messages_remaining": 6990,
            "historical_credit_remaining": 0,
            "plan_ids": ["lite"],
        },
    )
    data = portal.analytics("last_7_days")
    assert data["credits_total"] == 7000
    assert data["messages_total"] == 7000
    assert data["intended_message_mrr_usd"] == intended_price_usd("lite")
    assert data["live_checkout_mrr_usd"] == PLAN_PRICES_USD["lite"]


@pytest.mark.asyncio
async def test_owner_copilot_publish_consumes_daily_edit(monkeypatch):
    from services.billing.membership.daily_edits import reset_daily_edits_for_tests, set_platform_baseline, status
    from services.owner_copilot.tools_write import tool_publish_cm

    reset_daily_edits_for_tests()
    try:
        set_platform_baseline(1)
        monkeypatch.setattr(
            "services.owner_copilot.tools_write.resolve_permissions",
            lambda *_a, **_k: {"contentPublish": True},
        )

        async def _publish_ok(**_kwargs):
            return {"content_version_id": "v1"}

        monkeypatch.setattr("services.ai_setup.publish.publish_draft", _publish_ok)
        first = await tool_publish_cm(tenant_id="pub-shop", role="owner", confirmed=True)
        assert first.ok is True
        assert status("pub-shop").used == 1
        blocked = await tool_publish_cm(tenant_id="pub-shop", role="owner", confirmed=True)
        assert blocked.ok is False
        assert blocked.error == "AI_SETUP_DAILY_LIMIT"
    finally:
        reset_daily_edits_for_tests()


def test_range_start_last_week_is_previous_calendar_week():
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)  # Monday

    assert portal._range_start("last_week", now).isoformat() == "2026-08-10T00:00:00+00:00"
