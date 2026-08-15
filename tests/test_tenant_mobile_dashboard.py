"""Tenant mobile Dashboard composition + API authorization tests."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services.credit_ledger_service import CreditLedgerService
from services.entitlements_service import EntitlementsStore
from services.tenant_mobile_dashboard.compose import build_tenant_mobile_dashboard
from services.tenant_mobile_dashboard.periods import (
    PeriodValidationError,
    TimezoneValidationError,
    parse_period,
    parse_timezone,
    resolve_period_window,
)
from services.tenant_mobile_dashboard.status import derive_workspace_status
from services.tenant_mobile_dashboard.usage import aggregate_tenant_usage


def _write_flow(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


@pytest.fixture()
def ledger_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> EntitlementsStore:
    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    ledger = CreditLedgerService(root=tmp_path / "ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.credit_ledger_service",
        ledger,
    )
    return store


def test_period_and_timezone_validation() -> None:
    assert parse_period("7d") == "7d"
    assert parse_period("custom") == "custom"
    with pytest.raises(PeriodValidationError):
        parse_period("year")
    tz = parse_timezone("UTC")
    with pytest.raises(TimezoneValidationError):
        parse_timezone("Not/AZone")
    window = resolve_period_window(period="7d", tz=tz, current_period_end=None)
    assert window["period"] == "7d"
    assert window["start_ts"] < window["end_ts"]
    custom = resolve_period_window(
        period="custom",
        tz=tz,
        current_period_end=None,
        custom_start="2026-08-01",
        custom_end="2026-08-13",
    )
    assert custom["period"] == "custom"
    assert custom["start_ts"] < custom["end_ts"]


def test_today_is_full_local_calendar_day() -> None:
    tz = parse_timezone("Asia/Beirut")
    now = datetime(2026, 8, 15, 12, 35, tzinfo=tz)
    assert parse_period("today") == "today"
    window = resolve_period_window(period="today", tz=tz, current_period_end=None, now=now)
    assert window["period"] == "today"
    assert window["end_ts"] - window["start_ts"] == 24 * 3600
    noon = datetime(2026, 8, 15, 12, 0, tzinfo=tz)
    assert window["start_ts"] <= noon.timestamp() < window["end_ts"]

    same_day = resolve_period_window(
        period="custom",
        tz=tz,
        current_period_end=None,
        now=now,
        custom_start="2026-08-15",
        custom_end="2026-08-15",
    )
    assert same_day["end_ts"] - same_day["start_ts"] == 24 * 3600

    utc = parse_timezone("UTC")
    early = datetime(2026, 8, 16, 1, 0, tzinfo=tz)
    today_utc = resolve_period_window(period="today", tz=utc, current_period_end=None, now=early)
    assert today_utc["start_ts"] < today_utc["end_ts"]
    assert today_utc["start_ts"] <= early.astimezone(UTC).timestamp() < today_utc["end_ts"]


def test_today_activity_includes_local_noon_replies() -> None:
    from services.tenant_mobile_dashboard.activity import build_activity_summary

    tz = parse_timezone("Asia/Beirut")
    now = datetime(2026, 8, 15, 12, 35, tzinfo=tz)
    window = resolve_period_window(period="today", tz=tz, current_period_end=None, now=now)
    noon = datetime(2026, 8, 15, 12, 0, tzinfo=tz)
    payload = build_activity_summary(
        "acme",
        start_ts=window["start_ts"],
        end_ts=window["end_ts"],
        integrations=[{"platform": "instagram", "connected": True}],
        entries=[
            {
                "timestamp": noon.astimezone(UTC).isoformat().replace("+00:00", "Z"),
                "tenant_id": "acme",
                "channel": "instagram",
                "source": "qa_database",
                "bot_to_user": True,
            }
        ],
    )
    assert payload["total_activity"]["messages_replied"] == 1
    assert payload["total_activity"]["smart_answers"] == 1


def test_last_month_dashboard_survives_corrupt_owner_chat_meta(
    ledger_env: EntitlementsStore,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.credit_ledger_service import credit_ledger_service
    from services.owner_chat_store import OwnerChatStore

    tenant_id = "t_last_month_corrupt"
    ledger_env.set_plan(tenant_id=tenant_id, plan_id="starter", status="active", source="admin")
    credit_ledger_service.ensure_period_grant(tenant_id)
    store = OwnerChatStore(root=tmp_path / "owner_chat")
    conv = store.create_conversation(tenant_id=tenant_id, user_id="u1", greeting_text="Hi")
    store.append_message(
        tenant_id=tenant_id,
        user_id="u1",
        conversation_id=conv.id,
        role="user",
        content="Hello",
    )
    path = store._conv_path(tenant_id, conv.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = "bad"
    payload["updated_at"] = "bad"
    path.write_text(json.dumps(payload), encoding="utf-8")

    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.copilot.OwnerChatStore",
        lambda *args, **kwargs: store,
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.platform_owner_service.is_suspended",
        lambda _tid: False,
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.compute_cm_progress",
        lambda _tid: {
            "sections_total": 10,
            "sections_present": 8,
            "sections_missing": [],
            "sections_filled": ["ai_basics"],
            "sections_weak": [],
            "sections_truly_missing": [],
            "published": True,
            "percent": 80,
        },
    )
    monkeypatch.setattr(
        "services.integration_capabilities.list_tenant_integration_status",
        lambda _tid: [{"platform": "instagram", "connected": True}],
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.aggregate_tenant_usage",
        lambda *_a, **_k: {"status": "empty", "total_interactions": 0, "distribution": []},
    )
    monkeypatch.setattr("services.user_service.user_service.get_user_by_id", lambda _uid: {"name": "Owner"})
    monkeypatch.setattr(
        "services.user_service.user_service.get_all_users",
        lambda: [{"id": "u1", "tenantId": tenant_id, "role": "owner", "email": "o@x.com", "status": "active"}],
    )

    dashboard = build_tenant_mobile_dashboard(
        tenant_id=tenant_id,
        user_id="u1",
        period_raw="last_month",
        timezone_raw="Asia/Beirut",
    )
    assert dashboard["period"]["id"] == "last_month"
    assert dashboard["activity_summary"]["availability"] == "ok"
    assert "owner_copilot" in dashboard["activity_summary"]


def test_zero_credits_vs_missing_credit_data(ledger_env: EntitlementsStore, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger_env.set_plan(tenant_id="t_zero", plan_id="starter", status="active", source="admin")
    from services.credit_ledger_service import credit_ledger_service

    credit_ledger_service.ensure_period_grant("t_zero")
    # Drain available to real zero.
    path = credit_ledger_service._balance_path("t_zero")
    path.write_text(json.dumps({"available": 0, "reserved": 0, "updated_at": time.time()}), encoding="utf-8")

    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.platform_owner_service.is_suspended",
        lambda _tid: False,
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.compute_cm_progress",
        lambda _tid: {
            "sections_total": 10,
            "sections_present": 8,
            "sections_missing": [],
            "sections_filled": ["ai_basics"],
            "sections_weak": [],
            "sections_truly_missing": [],
            "published": True,
            "percent": 80,
        },
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.channels.list_tenant_integration_status",
        lambda _tid: [{"platform": "instagram", "connected": True}],
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.channels.capability_state",
        lambda *_a, **_k: {
            "requested_enabled": True,
            "permission_present": True,
            "webhook_subscribed": True,
            "connection_healthy": True,
            "effective_enabled": True,
            "live_verified": True,
            "blocker_code": None,
            "blocker_message": None,
            "status": "live_verified",
        },
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.aggregate_tenant_usage",
        lambda *_a, **_k: {"status": "empty", "total_interactions": 0, "distribution": []},
    )
    monkeypatch.setattr(
        "services.user_service.user_service.get_user_by_id",
        lambda _uid: {"businessName": "Zero Clinic", "name": "Owner"},
    )
    monkeypatch.setattr(
        "services.user_service.user_service.get_all_users",
        lambda: [{"id": "u1", "tenantId": "t_zero", "role": "owner", "email": "o@x.com", "status": "active"}],
    )

    payload = build_tenant_mobile_dashboard(tenant_id="t_zero", user_id="u1", period_raw="30d", timezone_raw="UTC")
    assert payload["plan_and_credits"]["availability"] == "ok"
    assert payload["plan_and_credits"]["available_credits"] == 0
    assert payload["plan_and_credits"]["actions"]["upgrade_plan"] is True
    assert payload["workspace_status"]["state"] == "credits_depleted"
    blob = json.dumps(payload).lower()
    assert "cost_usd" not in blob
    assert "provider_cost" not in blob
    assert payload["privacy"]["excludes_openai_usd"] is True


def test_max_plan_hides_upgrade_action(ledger_env: EntitlementsStore) -> None:
    ledger_env.set_plan(tenant_id="t_max", plan_id="max", status="active", source="admin")
    from services.credit_ledger_service import credit_ledger_service
    from services.tenant_mobile_dashboard.compose import _plan_and_credits

    credit_ledger_service.ensure_period_grant("t_max")
    section = _plan_and_credits("t_max")
    assert section["availability"] == "ok"
    assert section["plan_id"] == "max"
    assert section["actions"]["upgrade_plan"] is False
    assert section["actions"]["buy_credits"] is True


def test_no_subscription_status(ledger_env: EntitlementsStore, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.platform_owner_service.is_suspended",
        lambda _tid: False,
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.compute_cm_progress",
        lambda _tid: {
            "sections_total": 10,
            "sections_present": 0,
            "sections_missing": ["ai_basics"],
            "sections_filled": [],
            "sections_weak": [],
            "sections_truly_missing": ["ai_basics"],
            "published": False,
            "percent": 0,
        },
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.channels.build_channel_breakdown",
        lambda *_a, **_k: {
            "any_connected": False,
            "connection_issue": False,
            "dm_operational": False,
            "channels": [],
            "membership_allows_comments": False,
        },
    )
    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.compose.aggregate_tenant_usage",
        lambda *_a, **_k: {"status": "empty", "total_interactions": 0, "distribution": []},
    )
    monkeypatch.setattr("services.user_service.user_service.get_user_by_id", lambda _uid: {"name": "New"})
    monkeypatch.setattr("services.user_service.user_service.get_all_users", lambda: [])

    payload = build_tenant_mobile_dashboard(tenant_id="t_none", user_id="u1")
    assert payload["workspace_status"]["state"] == "subscription_issue"
    assert payload["plan_and_credits"]["has_subscription"] is False


def test_usage_buckets_and_empty(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    log = tmp_path / "flow.jsonl"
    _write_flow(
        log,
        [
            {
                "timestamp": (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "acme",
                "channel": "instagram",
                "source": "gpt",
            },
            {
                "timestamp": (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "acme",
                "channel": "instagram_comment",
                "source": "gpt",
            },
            {
                "timestamp": (now - timedelta(hours=2, minutes=30)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "acme",
                "channel": "web",
                "source": "web_chat",
            },
            {
                "timestamp": (now - timedelta(hours=3)).isoformat().replace("+00:00", "Z"),
                "tenant_id": "other",
                "channel": "facebook",
                "source": "gpt",
            },
        ],
    )
    start = (now - timedelta(days=1)).timestamp()
    end = (now + timedelta(minutes=1)).timestamp()
    usage = aggregate_tenant_usage("acme", start_ts=start, end_ts=end, log_path=str(log))
    assert usage["status"] == "ok"
    assert usage["instagram_dms"] == 1
    assert usage["instagram_comments"] == 1
    assert usage["web_dms"] == 1
    assert usage["facebook_dms"] == 0
    assert usage["credits_by_bucket_available"] is False

    empty = aggregate_tenant_usage("nobody", start_ts=start, end_ts=end, log_path=str(log))
    assert empty["status"] == "empty"


def test_comments_plan_gate_and_dm_ok_comments_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.tenant_mobile_dashboard.channels import build_channel_breakdown

    monkeypatch.setattr(
        "services.tenant_mobile_dashboard.channels.list_tenant_integration_status",
        lambda _tid: [
            {"platform": "instagram", "connected": True},
            {"platform": "facebook", "connected": False},
        ],
    )

    def _cap(tenant_id: str, platform: str, capability: str) -> dict[str, Any]:
        if capability == "dm" and platform == "instagram":
            return {
                "requested_enabled": True,
                "permission_present": True,
                "webhook_subscribed": True,
                "connection_healthy": True,
                "effective_enabled": True,
                "live_verified": True,
                "blocker_code": None,
                "blocker_message": None,
                "status": "live_verified",
            }
        if capability == "comments" and platform == "instagram":
            return {
                "requested_enabled": True,
                "permission_present": False,
                "webhook_subscribed": False,
                "connection_healthy": True,
                "effective_enabled": False,
                "live_verified": False,
                "blocker_code": "missing_comment_permissions",
                "blocker_message": "Missing Meta comment permissions",
                "status": "permission_required",
            }
        return {
            "requested_enabled": False,
            "permission_present": False,
            "webhook_subscribed": False,
            "connection_healthy": False,
            "effective_enabled": False,
            "live_verified": False,
            "blocker_code": "connect_channel_first",
            "blocker_message": "Connect first",
            "status": "disabled",
        }

    monkeypatch.setattr("services.tenant_mobile_dashboard.channels.capability_state", _cap)

    lite = build_channel_breakdown(
        "t1",
        features={"comment_automation": False},
        usage={"instagram_dms": 3, "facebook_dms": 0, "instagram_comments": 0, "facebook_comments": 0},
    )
    ig_comments = next(c for c in lite["channels"] if c["platform"] == "instagram" and c["capability"] == "comments")
    assert ig_comments["membership_allows"] is False
    assert ig_comments["blocker_code"] == "plan_comments_disabled"

    starter = build_channel_breakdown(
        "t1",
        features={"comment_automation": True},
        usage={"instagram_dms": 3, "facebook_dms": 0, "instagram_comments": 0, "facebook_comments": 0},
    )
    ig_dm = next(c for c in starter["channels"] if c["platform"] == "instagram" and c["capability"] == "dm")
    ig_comments2 = next(
        c for c in starter["channels"] if c["platform"] == "instagram" and c["capability"] == "comments"
    )
    assert ig_dm["operational"] is True
    assert ig_comments2["operational"] is False
    assert ig_comments2["blocker_code"] == "missing_comment_permissions"


def test_workspace_status_suspended_and_active() -> None:
    suspended = derive_workspace_status(
        suspended=True,
        plan_id="starter",
        subscription_status="active",
        subscription_exempt=False,
        available_credits=1000,
        included_credits=1000,
        credits_known=True,
        cm_published=True,
        cm_percent=100,
        any_connected=True,
        connection_issue=False,
        dm_ok=True,
    )
    assert suspended["state"] == "suspended"

    active = derive_workspace_status(
        suspended=False,
        plan_id="growth",
        subscription_status="active",
        subscription_exempt=False,
        available_credits=5000,
        included_credits=10000,
        credits_known=True,
        cm_published=True,
        cm_percent=90,
        any_connected=True,
        connection_issue=False,
        dm_ok=True,
    )
    assert active["state"] == "active"
    assert active["reason_code"] == "workspace_active"


def test_mobile_dashboard_api_auth_and_tenant_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")

    import modules.mobile_dashboard_api  # noqa: F401
    from modules.core import app
    from services.dashboard_session_service import session_service

    client = TestClient(app)
    denied = client.get("/api/mobile/dashboard")
    assert denied.status_code == 401

    session = session_service.create_session(
        user_id="u-dash",
        email="dash@example.com",
        role="admin",
        permissions=None,
        tenant_id="tenant-a",
    )
    token = session_service.cookie_value_for(session)

    def _fake_dashboard(**kwargs):
        from services.tenant_mobile_dashboard.periods import parse_period, parse_timezone

        parse_period(kwargs.get("period_raw"))
        parse_timezone(kwargs.get("timezone_raw"))
        return {
            "success": True,
            "generated_at": "2026-08-11T00:00:00Z",
            "tenant_echo": kwargs["tenant_id"],
            "period": {"id": "billing", "label": "x", "timezone": "UTC", "start": "a", "end": "b"},
            "workspace": {"tenant_id": kwargs["tenant_id"], "workspace_name": "A"},
            "workspace_status": {
                "state": "active",
                "reason_code": "workspace_active",
                "title": "Active",
                "explanation": "ok",
                "primary_action": None,
            },
            "plan_and_credits": {"availability": "ok"},
            "usage_summary": {"availability": "empty"},
            "usage_distribution": {"availability": "empty", "items": []},
            "channels": {"availability": "ok", "channels": []},
            "content_readiness": {"availability": "ok"},
            "team_capacity": {"availability": "ok"},
            "alerts": [],
            "partial_failures": [],
            "privacy": {"excludes_openai_usd": True},
        }

    monkeypatch.setattr("modules.mobile_dashboard_api.build_tenant_mobile_dashboard", _fake_dashboard)

    ok = client.get(
        "/api/mobile/dashboard?period=7d&tz=UTC",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["tenant_echo"] == "tenant-a"
    assert body["success"] is True

    session_service.revoke_session(token)
    session2 = session_service.create_session(
        user_id="u-no",
        email="no@example.com",
        role="viewer",
        permissions={"dashboard": False},
        tenant_id="tenant-a",
    )
    token2 = session_service.cookie_value_for(session2)
    forbidden = client.get(
        "/api/mobile/dashboard",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert forbidden.status_code == 403

    session_service.revoke_session(token2)
    session3 = session_service.create_session(
        user_id="u-ok",
        email="ok@example.com",
        role="admin",
        permissions=None,
        tenant_id="tenant-a",
    )
    token3 = session_service.cookie_value_for(session3)
    bad_period = client.get(
        "/api/mobile/dashboard?period=year",
        headers={"Authorization": f"Bearer {token3}"},
    )
    assert bad_period.status_code == 400
