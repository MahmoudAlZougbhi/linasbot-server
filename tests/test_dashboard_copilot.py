"""Owner Copilot Dashboard totals must be real and add up per user."""

from __future__ import annotations

import json
import time
from pathlib import Path

from services.owner_ai_model_router import OwnerChatUsageTracker, RouteDecision
from services.owner_chat_store import OwnerChatStore
from services.tenant_mobile_dashboard.activity import build_activity_summary
from services.tenant_mobile_dashboard.copilot import build_owner_copilot_summary, credits_from_tokens


def _route() -> RouteDecision:
    return RouteDecision(kind="owner_help", model="test", reason="test", max_context_tokens=0)


def _seed_chat(store: OwnerChatStore, *, tenant_id: str, user_id: str, ts: float) -> str:
    conv = store.create_conversation(tenant_id=tenant_id, user_id=user_id, greeting_text="Hi")
    store.append_message(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conv.id,
        role="user",
        content="Hello Linas",
    )
    path = store._conv_path(tenant_id, conv.id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["created_at"] = ts
    payload["updated_at"] = ts
    path.write_text(json.dumps(payload), encoding="utf-8")
    return conv.id


def test_credits_from_tokens_matches_log_estimate() -> None:
    assert credits_from_tokens(0) == 0
    assert credits_from_tokens(100) == 1
    assert credits_from_tokens(250) == 2


def test_copilot_per_user_rows_sum_to_footer(tmp_path: Path, monkeypatch) -> None:
    store = OwnerChatStore(root=tmp_path / "owner_chat")
    tracker = OwnerChatUsageTracker(root=tmp_path / "owner_ai_usage")
    monkeypatch.setattr("services.tenant_mobile_dashboard.copilot.owner_chat_usage_tracker", tracker)
    monkeypatch.setattr(
        "services.user_service.user_service.get_user_by_id",
        lambda uid: {"id": uid, "name": f"User {uid}", "displayName": f"User {uid}"},
    )

    now = time.time()
    start = now - 86400
    end = now + 60
    cid_a = _seed_chat(store, tenant_id="acme", user_id="u-owner", ts=now - 10)
    cid_b = _seed_chat(store, tenant_id="acme", user_id="u-owner", ts=now - 20)
    cid_c = _seed_chat(store, tenant_id="acme", user_id="u-staff", ts=now - 30)

    tracker.record(
        tenant_id="acme",
        user_id="u-owner",
        conversation_id=cid_a,
        route=_route(),
        prompt_tokens=800,
        completion_tokens=200,
    )
    tracker.record(
        tenant_id="acme",
        user_id="u-staff",
        conversation_id=cid_c,
        route=_route(),
        prompt_tokens=400,
        completion_tokens=100,
    )

    summary = build_owner_copilot_summary(
        "acme",
        start_ts=start,
        end_ts=end,
        log_credits_by_conversation={cid_b: 7},
        log_credits_unmapped=2,
        log_interactions=3,
        store=store,
    )
    assert summary["chats"] == 3
    assert summary["users"] == 2
    assert sum(row["chats"] for row in summary["by_user"]) == summary["chats"]
    assert sum(row["credits"] for row in summary["by_user"]) == summary["credits"]
    by_id = {row["user_id"]: row for row in summary["by_user"] if row.get("user_id")}
    assert by_id["u-owner"]["chats"] == 2
    assert by_id["u-staff"]["chats"] == 1
    assert by_id["u-owner"]["credits"] == credits_from_tokens(1000) + 7
    assert by_id["u-staff"]["credits"] == credits_from_tokens(500)
    unattr = next(row for row in summary["by_user"] if row.get("unattributed"))
    assert unattr["credits"] == 2
    assert "owner_ai_usage" in summary["credits_source"]


def test_activity_includes_tiktok_zero_row() -> None:
    now = time.time()
    payload = build_activity_summary(
        "t-dash-tiktok-zero",
        start_ts=now - 100,
        end_ts=now + 100,
        integrations=[{"platform": "instagram", "connected": True}],
        entries=[],
    )
    platforms = [row["platform"] for row in payload["channels"]]
    assert platforms == ["instagram", "facebook", "tiktok", "whatsapp"]
    tiktok = next(row for row in payload["channels"] if row["platform"] == "tiktok")
    assert tiktok["messages"] == 0
    assert tiktok["connected"] is False
