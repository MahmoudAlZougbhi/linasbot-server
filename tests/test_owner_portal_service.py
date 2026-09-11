from __future__ import annotations

from datetime import UTC, datetime

import pytest

import services.interaction_flow_logger as flow_logger
import services.owner_portal_service as portal


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
    assert rows[0]["credits_used"] == 45
    assert rows[0]["credits_remaining"] == 75
    assert rows[0]["intended_included_messages"] == 3000
    assert rows[0]["intended_price_usd"] == 59.0


def test_daily_edit_zero_limit_blocks_reserve() -> None:
    from services.membership.daily_edits import (
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
    monkeypatch.setattr(portal, "user_service", type("U", (), {"get_all_users": staticmethod(lambda: [])})())
    monkeypatch.setattr(portal, "get_recent_flows", lambda limit=500: [])
    monkeypatch.setattr(
        portal,
        "list_subscribers",
        lambda _users: [
            {
                "subscription": "lite",
                "membership": "active",
                "credits_total": 7000,
                "credits_used": 10,
                "credits_remaining": 6990,
            }
        ],
    )
    data = portal.analytics("last_7_days")
    assert data["credits_total"] == 7000
    assert data["intended_message_mrr_usd"] == 10.0
    assert data["live_checkout_mrr_usd"] != data["intended_message_mrr_usd"]


@pytest.mark.asyncio
async def test_owner_copilot_publish_consumes_daily_edit(monkeypatch):
    from services.membership.daily_edits import reset_daily_edits_for_tests, set_platform_baseline, status
    from services.owner_ai_tools_write import tool_publish_cm

    reset_daily_edits_for_tests()
    try:
        set_platform_baseline(1)
        monkeypatch.setattr(
            "services.owner_ai_tools_write.resolve_permissions",
            lambda *_a, **_k: {"contentPublish": True},
        )

        async def _publish_ok(**_kwargs):
            return {"content_version_id": "v1"}

        monkeypatch.setattr("services.cm.publish.publish_draft", _publish_ok)
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
