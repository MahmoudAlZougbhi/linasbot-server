"""Prod QA failures from 2026-10-07."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from modules.flow_api import newest_first
from scripts.owner_portal_junk_tenants import candidate_rows
from scripts.owner_portal_junk_tenants import main as junk_main
from services.billing.membership.activation_readiness import _alembic_head
from services.owner_portal.audit_feed import merged_audit_events
from services.owner_portal.flow_counts import accumulate_channel_counts
from services.owner_portal.franco import to_franco
from services.owner_portal.owner_portal_service import analytics
from services.owner_portal.owner_qa import _THRESHOLD, match_owner_qa
from services.owner_portal.owner_traces import _write
from services.owner_portal.platform_brain_lab import customer_lab_turn, hint_for, observe_lab_turn
from services.team.tenant_identity import is_junk_identity, validate_tenant_identity


def test_hint_for_every_stopped_reason() -> None:
    assert "fail-closed" in hint_for("failed_closed", has_reply=False)
    assert hint_for("unpublished", has_reply=False)
    assert hint_for("something_new", has_reply=False)
    assert hint_for("failed_closed", has_reply=True) == ""


@pytest.mark.asyncio
async def test_lab_turn_records_trace_and_flow_without_outbox(monkeypatch) -> None:
    traces: list[dict] = []
    flows: list[dict] = []
    monkeypatch.setattr(
        "services.owner_portal.platform_brain_lab.known_tenant_id",
        lambda tenant_id: tenant_id,
    )
    monkeypatch.setattr("services.owner_portal.owner_traces.write_trace", traces.append)
    monkeypatch.setattr(
        "services.owner_copilot.interaction_flow_logger.log_interaction",
        lambda *args, **kwargs: flows.append(kwargs),
    )

    async def _reply(**_kwargs):
        return SimpleNamespace(reply="", reason="failed_closed", stop=True, model="")

    monkeypatch.setattr("services.brain.reply.orchestrator.run_customer_reply_v2_dm", _reply)

    def _boom(*_args, **_kwargs):
        raise AssertionError("lab must not enqueue an outbox send")

    monkeypatch.setattr("services.brain.outbox.enqueue_envelope", _boom)
    result = await customer_lab_turn(
        actor_user_id="owner",
        tenant_id="testuser",
        message="hello",
        mode="live",
    )
    assert result["hint"]
    assert traces[0]["channel"] == "brains_test"
    assert traces[0]["brain"] == "customer"
    assert flows[0]["channel"] == "brains_test"


def test_trace_write_error_is_logged(monkeypatch, caplog) -> None:
    def _boom(*_args, **_kwargs):
        raise RuntimeError("db down")

    monkeypatch.setattr("db.session.whatsapp_session", _boom)
    with caplog.at_level(logging.ERROR):
        assert _write({"tenant_id": "linas", "brain": "customer"}) == ""
    assert "owner message trace was not stored" in caplog.text


def test_qa_matches_paraphrase_and_rejects_unrelated(monkeypatch) -> None:
    stored = [
        {
            "id": "qa1",
            "variants": [
                {"language": "en", "question": "what is the purple lantern support code?", "answer": "7781"},
                {"language": "ar", "question": "ما هو رمز الدعم", "answer": "7781"},
                {"language": "franco", "question": "shou huwe ramz el daam", "answer": "7781"},
            ],
        }
    ]
    from contextlib import contextmanager

    @contextmanager
    def _session():
        yield object()

    monkeypatch.setattr("services.owner_portal.owner_qa.list_qa", lambda: stored)
    monkeypatch.setattr("services.owner_portal.owner_qa.embed_one", lambda *_a, **_k: [0.1, 0.2])
    monkeypatch.setattr("services.owner_portal.owner_qa._session", _session)

    class _Item:
        def __init__(self, score: float, source_id: str) -> None:
            self.score = score
            self.source_id = source_id

    class _Found:
        def __init__(self, score: float) -> None:
            self.items = [_Item(score, "qa1:en")]

    scores = {"tell me the purple lantern support code please": 0.8, "what is the weather": 0.2}

    def _similar(*_args, **_kwargs):
        return _Found(0.8)

    monkeypatch.setattr("services.brain.search.store.query_similar", _similar)
    hit = match_owner_qa("Tell me the purple lantern support code please", "en")
    assert hit and hit["hit"] == "semantic" and hit["answer"] == "7781"
    assert hit["score"] >= _THRESHOLD

    def _miss(*_args, **_kwargs):
        return _Found(scores["what is the weather"])

    monkeypatch.setattr("services.brain.search.store.query_similar", _miss)
    assert match_owner_qa("what is the weather", "en") is None
    assert match_owner_qa("ما هو رمز الدعم", "ar")["hit"] == "exact"


def test_franco_variant_is_latin(monkeypatch) -> None:
    assert not any("\u0600" <= char <= "\u06ff" for char in to_franco("شو هو كود الدعم"))
    assert to_franco("shou") == "shou"


@pytest.mark.asyncio
async def test_platform_owner_qa_is_not_credit_blocked(monkeypatch) -> None:
    from services.owner_copilot.brain import iter_owner_turn_v2_events

    monkeypatch.setattr("services.owner_copilot.brain.owner_copilot_v2_enabled", lambda: True)
    monkeypatch.setattr(
        "services.owner_portal.owner_qa.match_owner_qa",
        lambda *_a, **_k: {"answer": "7781", "score": 1.0, "qa_id": "qa1"},
    )
    monkeypatch.setattr("services.billing.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: True)
    events = []
    async for event in iter_owner_turn_v2_events(
        tenant_id="shop",
        user_id="u",
        role="owner",
        conversation_id="c",
        user_text="tell me the code",
    ):
        events.append(event)
    assert events[0].type == "done"
    assert events[0].payload["route"]["reason"] == "qa_hit"


@pytest.mark.asyncio
async def test_zero_credit_tenant_still_pauses_without_qa(monkeypatch) -> None:
    from services.owner_copilot.brain import iter_owner_turn_v2_events

    monkeypatch.setattr("services.owner_copilot.brain.owner_copilot_v2_enabled", lambda: True)
    monkeypatch.setattr("services.owner_portal.owner_qa.match_owner_qa", lambda *_a, **_k: None)
    monkeypatch.setattr("services.billing.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "services.billing.credit_ai_gate.owner_credits_paused_payload",
        lambda *_a, **_k: {"code": "insufficient_messages"},
    )
    monkeypatch.setattr(
        "services.owner_copilot.message_billing.estimate_copilot_cost_usd",
        lambda **_k: 0,
    )
    events = []
    async for event in iter_owner_turn_v2_events(
        tenant_id="shop",
        user_id="u",
        role="owner",
        conversation_id="c",
        user_text="hello",
    ):
        events.append(event)
    assert events[0].type == "credits_paused"


def test_audit_includes_lab_action(tmp_path, monkeypatch) -> None:
    from services.team.platform_owner_service import PlatformOwnerService

    service = PlatformOwnerService(root=tmp_path)
    service.log_action(actor_user_id="owner", action="brain_lab_customer", tenant_id="linas", details={})
    monkeypatch.setattr("services.team.platform_owner_service.platform_owner_service", service)
    monkeypatch.setattr("services.billing.membership.catalog_admin.audit_log", lambda: [])
    events = merged_audit_events()
    assert events[0]["action"] == "brain_lab_customer"


def test_analytics_matches_user_rows_and_rejects_all(monkeypatch) -> None:
    monkeypatch.setattr(
        "services.owner_portal.owner_portal_service.list_subscribers",
        lambda _users: [
            {
                "subscription": "lite",
                "membership": "active",
                "credits_total": 24994,
                "credits_used": 0,
                "credits_remaining": 24994,
                "messages_total": 24994,
                "messages_used": 0,
                "messages_remaining": 24994,
                "historical_credit_remaining": 180858,
            }
        ],
    )
    monkeypatch.setattr(
        "services.team.user_tenant_query.list_users_capped",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "services.owner_portal.flow_counts.channel_counts_for_range",
        lambda *_a, **_k: {"messages_by_channel": {}, "comments": 0},
    )
    monkeypatch.setattr("services.owner_portal.analytics_sql.load_overview", lambda *_a, **_k: None)
    data = analytics("last_7_days")
    assert data["credits_total"] == 24994
    assert data["messages_total"] == 24994
    assert data["historical_credit_remaining"] == 180858
    with pytest.raises(ValueError, match="Unsupported date range"):
        analytics("all")


def test_channel_counts_are_not_capped_at_500() -> None:
    now = datetime.now(UTC).isoformat()
    rows = [{"channel": "whatsapp", "message_type": "text", "timestamp": now} for _ in range(600)]
    counted = accumulate_channel_counts(rows)
    assert counted["messages_by_channel"]["whatsapp"] == 600


def test_activity_flow_is_newest_first() -> None:
    ordered = newest_first(
        [
            {"timestamp": "2026-09-07T00:00:00Z", "tenant_id": "a"},
            {"timestamp": "2026-10-07T00:00:00Z", "tenant_id": "b"},
        ]
    )
    assert ordered[0]["tenant_id"] == "b"


@pytest.mark.asyncio
async def test_unknown_tenant_on_daily_edits_and_flows(monkeypatch) -> None:
    from modules.platform_message_api import platform_daily_edits, platform_message_flows

    monkeypatch.setattr("modules.platform_message_api.require_platform_owner", lambda _request: None)
    monkeypatch.setattr("services.owner_portal.analytics_sql.tenant_is_known", lambda tid: tid == "linas")
    with pytest.raises(HTTPException) as unknown:
        await platform_daily_edits(request=None, tenant_id="qa-no-such-tenant-xyz")
    assert unknown.value.status_code == 404
    monkeypatch.setattr(
        "services.billing.membership.daily_edits.status",
        lambda _tid: SimpleNamespace(),
    )
    monkeypatch.setattr("services.billing.membership.daily_edits.decision_payload", lambda _d: {"code": "ok"})
    known = await platform_daily_edits(request=None, tenant_id="linas")
    assert known["success"] is True
    empty = await platform_daily_edits(request=None, tenant_id="")
    assert empty["success"] is True
    with pytest.raises(HTTPException) as flows:
        await platform_message_flows(request=None, tenant_id="qa-no-such-tenant-xyz", limit=50)
    assert flows.value.status_code == 404


def test_alembic_expected_head_matches_scripts() -> None:
    report = _alembic_head()
    assert report["ok"] is True
    assert report["expected"] == report["heads"][0]
    assert report["expected"] != "20260910_req_web_chat"


def test_signup_rejects_junk_and_accepts_arabic() -> None:
    with pytest.raises(ValueError):
        validate_tenant_identity(tenant_id="script-x-script", business_name="Shop")
    with pytest.raises(ValueError):
        validate_tenant_identity(tenant_id="x-or-1-1", business_name="Shop")
    with pytest.raises(ValueError):
        validate_tenant_identity(tenant_id="http-169-254-169-254-latest-meta-data", business_name="Shop")
    with pytest.raises(ValueError):
        validate_tenant_identity(tenant_id="linas", business_name="sqli'-- -")
    with pytest.raises(ValueError):
        validate_tenant_identity(tenant_id="linas", business_name="<script>x</script>")
    with pytest.raises(ValueError):
        validate_tenant_identity(tenant_id="linas", email='"<img src=x onerror=alert(1)>"@x.com')
    assert validate_tenant_identity(tenant_id="layla-salon", business_name="صالون ليلى") == "layla-salon"
    assert is_junk_identity(tenant_id="linas", business_name="<script>") is False


def test_junk_dry_run_changes_nothing(capsys) -> None:
    rows = [
        {"tenant_id": "script-x-script", "business_name": "<script>x</script>", "email": "a@x.com"},
        {"tenant_id": "linas", "business_name": "<script>", "email": "owner@linas.ai", "messages_remaining": 10},
        {"tenant_id": "real-shop", "business_name": "Real Shop", "email": "a@shop.com"},
    ]
    code = junk_main(["--rows-json", json.dumps(rows)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert [row["tenant_id"] for row in payload["candidates"]] == ["script-x-script"]
    assert candidate_rows(rows)[0]["tenant_id"] == "script-x-script"
    refused = junk_main(["--confirm", "--tenant-ids", "other", "--rows-json", json.dumps(rows)])
    assert refused == 2


def test_shared_chat_is_visible_without_the_local_file(tmp_path, monkeypatch) -> None:
    from services.owner_copilot.chat_store import OwnerChatStore

    payload = {
        "id": "conv1",
        "tenant_id": "platform",
        "user_id": "owner",
        "title": "QA-LINAS-TEST",
        "created_at": 1,
        "updated_at": 2,
        "deleted": False,
        "messages": [{"id": "m", "role": "assistant", "content": "hi", "created_at": 1}],
    }
    monkeypatch.setattr("services.owner_copilot.owner_chat_pg.load_conversation", lambda **_k: payload)
    monkeypatch.setattr(
        "services.owner_copilot.owner_chat_pg.list_conversations",
        lambda **_k: [payload],
    )
    store = OwnerChatStore(root=tmp_path)
    assert all(
        store.get_conversation(tenant_id="platform", user_id="owner", conversation_id="conv1") for _ in range(10)
    )
    assert store.list_conversations(tenant_id="platform", user_id="owner")[0]["id"] == "conv1"


def test_observe_lab_turn_calls_writer(monkeypatch) -> None:
    seen: list[dict] = []
    monkeypatch.setattr("services.owner_portal.owner_traces.write_trace", seen.append)
    monkeypatch.setattr("services.owner_copilot.interaction_flow_logger.log_interaction", lambda *_a, **_k: None)
    observe_lab_turn(tenant_id="linas", brain="copilot", message="hi", result={"reply": "ok", "reason": ""})
    assert seen[0]["brain"] == "owner_copilot"
    assert seen[0]["channel"] == "brains_test"
