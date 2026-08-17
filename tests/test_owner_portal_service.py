from __future__ import annotations

from datetime import UTC, datetime

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


def test_range_start_last_week_is_previous_calendar_week():
    now = datetime(2026, 8, 17, 12, tzinfo=UTC)  # Monday

    assert portal._range_start("last_week", now).isoformat() == "2026-08-10T00:00:00+00:00"
