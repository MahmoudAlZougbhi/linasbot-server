"""Tests for Interaction Logs detail fields and estimated cost persistence."""

from __future__ import annotations

from services import interaction_flow_logger as ifl
from services.model_pricing import COST_BASIS_TOKEN_RATES, compute_cost_from_usage


def test_compute_cost_from_usage_gpt4o_mini():
    costs = compute_cost_from_usage("gpt-4o-mini", 1_000_000, 1_000_000)
    assert costs["input_cost_usd"] == 0.15
    assert costs["output_cost_usd"] == 0.60
    assert costs["cost_usd"] == 0.75
    assert costs["cost_status"] == "estimated"
    assert costs["cost_basis"] == COST_BASIS_TOKEN_RATES


def test_resolve_interaction_channel_variants():
    assert ifl.resolve_interaction_channel({"_dashboard_test_simulation": True}) == "testing_lab"
    assert ifl.resolve_interaction_channel({"channel": "instagram"}) == "instagram"
    assert ifl.resolve_interaction_channel({"channel": "facebook"}) == "facebook"
    assert ifl.resolve_interaction_channel({"phone_number": "96170123456"}) == "whatsapp"


def test_log_interaction_persists_detail_and_cost(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERACTION_FLOW_DEBUG", "1")
    monkeypatch.delenv("FLOW_LOG_FULL_PROMPTS", raising=False)
    monkeypatch.setattr(ifl, "FLOW_LOG_FILE", str(tmp_path / "activity_flow.jsonl"))
    monkeypatch.setattr(ifl, "_FLOW_BUFFER", ifl.deque(maxlen=50))
    monkeypatch.setattr(ifl, "_INITIALIZED", False)

    ifl.log_interaction(
        user_id="96170123456",
        user_message="hello api_key=sk-secret123",
        bot_to_user="hi",
        source="gpt",
        user_phone="96170123456",
        user_data={"channel": "instagram"},
        conversation_id="conv-abc",
        handler_path="ai_orchestration",
        outcome="answer_question",
        model="gpt-5.4-mini",
        prompt_tokens=1000,
        completion_tokens=200,
        tokens=1200,
        cost_usd=0.00065,
        input_cost_usd=0.00025,
        output_cost_usd=0.0004,
        cost_status="estimated",
        cost_basis=COST_BASIS_TOKEN_RATES,
        ai_called=True,
        pipeline_decisions=[{"step": "action", "decision": "answer_question"}],
        cm_diagnostics={
            "reason": "packet_ready",
            "content_version_id": "cv1",
            "source_ids": ["svc.pricing"],
            "retrieved_sources": [{"source_id": "svc.pricing", "title": "Pricing"}],
        },
        flow_steps=[{"step": 1, "title": "User → Bot", "content": "hello"}],
    )
    entry = list(ifl._FLOW_BUFFER)[-1]
    assert entry["channel"] == "instagram"
    assert entry["direction"] == "inbound"
    assert entry["conversation_id"] == "conv-abc"
    assert entry["handler_path"] == "ai_orchestration"
    assert entry["outcome"] == "answer_question"
    assert entry["cost_usd"] == 0.00065
    assert entry["cost_status"] == "estimated"
    assert entry["cost_basis"] == COST_BASIS_TOKEN_RATES
    assert entry["prompt_tokens"] == 1000
    assert entry["completion_tokens"] == 200
    assert "sk-secret123" not in (entry.get("user_message") or "")
    assert "[REDACTED]" in (entry.get("user_message") or "")
    assert entry["cm_diagnostics"]["source_ids"] == ["svc.pricing"]
    assert entry["cm_diagnostics"]["retrieved_sources"][0]["title"] == "Pricing"


def test_faq_path_cost_status_none(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERACTION_FLOW_DEBUG", "1")
    monkeypatch.setattr(ifl, "FLOW_LOG_FILE", str(tmp_path / "activity_flow.jsonl"))
    monkeypatch.setattr(ifl, "_FLOW_BUFFER", ifl.deque(maxlen=50))
    monkeypatch.setattr(ifl, "_INITIALIZED", False)
    ifl.log_interaction(
        user_id="u1",
        user_message="price?",
        bot_to_user="100$",
        source="qa_database",
        ai_called=False,
        cost_status="none",
        faq_match={"faq_id": 12, "tier": "exact", "similarity": 1.0, "stored_language": "ar"},
    )
    entry = list(ifl._FLOW_BUFFER)[-1]
    assert entry["cost_status"] == "none"
    assert entry["cost_usd"] is None
    assert entry["faq_match"]["faq_id"] == 12


def test_historical_rows_get_unavailable_cost_status(monkeypatch, tmp_path):
    monkeypatch.setenv("INTERACTION_FLOW_DEBUG", "1")
    log_path = tmp_path / "activity_flow.jsonl"
    # Legacy GPT row without cost_status / cost_usd
    log_path.write_text(
        '{"timestamp":"2024-01-01T00:00:00Z","user_id":"...3456","source":"gpt","user_message":"hi","bot_to_user":"yo"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(ifl, "FLOW_LOG_FILE", str(log_path))
    monkeypatch.setattr(ifl, "_FLOW_BUFFER", ifl.deque(maxlen=50))
    monkeypatch.setattr(ifl, "_INITIALIZED", False)
    rows = ifl.get_recent_flows(limit=10)
    assert len(rows) == 1
    assert rows[0]["cost_status"] == "unavailable"
    assert rows[0]["channel"] == "unknown"
