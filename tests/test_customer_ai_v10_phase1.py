"""Customer AI V10 Phase 1 — safety, channel metadata, 90-minute history, metering."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def test_channel_metadata_comment_vs_dm():
    from services.customer_reply_v2.channel_metadata import build_channel_metadata

    dm = build_channel_metadata(channel="instagram_dm", conversation_id="c1", message_id="m1")
    assert dm["platform"] == "instagram"
    assert dm["surface"] == "dm"
    assert dm["is_public"] is False
    comment = build_channel_metadata(
        channel="facebook_comment",
        post_id="p1",
        comment_id="cmt1",
        account_id="page1",
    )
    assert comment["platform"] == "facebook"
    assert comment["surface"] == "comment"
    assert comment["is_public"] is True
    assert comment["post_id"] == "p1"


def test_history_window_default_is_90_minutes(v2_env):
    from services.customer_reply_v2.flags import dm_context_window_hours, dm_context_window_minutes

    assert abs(dm_context_window_hours() - 1.5) < 1e-9
    assert abs(dm_context_window_minutes() - 90) < 1e-9


def test_rolling_90_minute_cutoff():
    from services.customer_reply_v2.conversation_window import filter_rolling_window

    now = 1_700_000_000.0
    hour = 3600.0
    msgs = [
        {"role": "user", "content": "outside", "timestamp": now - (1.5 * hour) - 5},
        {"role": "user", "content": "inside", "timestamp": now - (1.5 * hour) + 5},
        {"role": "assistant", "content": "reply", "timestamp": now - 60},
    ]
    window = filter_rolling_window(msgs, now_ts=now, window_hours=1.5)
    contents = [m.content for m in window.messages]
    assert "outside" not in contents
    assert "inside" in contents
    assert "reply" in contents


def test_luna_and_tera_share_timestamped_history(v2_env):
    from services.customer_reply_v2.conversation_window import filter_rolling_window
    from services.customer_reply_v2.history_format import history_records_from_window, same_history_for_agents

    now = time.time()
    msgs = [
        {"role": "user", "content": "hi", "timestamp": now - 120},
        {"role": "assistant", "content": "hello", "timestamp": now - 60},
        {"role": "user", "content": "hours?", "timestamp": now - 10},
        {"role": "user", "content": "m4", "timestamp": now - 9},
        {"role": "user", "content": "m5", "timestamp": now - 8},
        {"role": "user", "content": "m6", "timestamp": now - 7},
        {"role": "user", "content": "m7", "timestamp": now - 6},
        {"role": "user", "content": "m8", "timestamp": now - 5},
    ]
    window = filter_rolling_window(msgs, now_ts=now, window_hours=1.5)
    luna = same_history_for_agents(history_records_from_window(window, channel="instagram_dm"))
    tera = same_history_for_agents(history_records_from_window(window, channel="instagram_dm"))
    assert luna == tera
    assert len(luna) == 8
    assert luna[0]["timestamp"]
    assert luna[0]["surface"] == "dm"
    assert luna[0]["sender"] == "customer"


@pytest.mark.asyncio
async def test_safety_gate_blocks_before_luna(v2_env, monkeypatch):
    await publish_test_content("t_safe", _rich_sections())
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.safety_gateway import SafetyDecision

    async def _block(**_k):
        return SafetyDecision(decision="block", reasons=["policy:csam"], provider="openai", incident_id="inc1")

    monkeypatch.setattr("services.safety_gateway.safety_gateway.check_text", _block)
    called = {"luna": False}

    async def _boom(**_k):
        called["luna"] = True
        raise AssertionError("Luna must not run after safety block")

    monkeypatch.setattr("services.customer_reply_v2.orchestrator.run_retrieval_luna", _boom)
    out = await run_customer_reply_v2_dm(
        tenant_id="t_safe",
        message="child sexual content",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
        provider_sender_id="u_safe",
    )
    assert called["luna"] is False
    assert out.reason == "safety_block"
    assert out.reply
    assert out.metadata.get("ai_called") is False
    assert out.metadata.get("safety_policy_version")


@pytest.mark.asyncio
async def test_safety_uncertain_does_not_block(v2_env, monkeypatch):
    await publish_test_content("t_unc", _rich_sections())
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.customer_reply_v2.safety_gate import CustomerSafetyDecision

    async def _unc(**_k):
        return CustomerSafetyDecision(blocked=False, certainty="uncertain", reasons=["unscanned_attachment:audio"])

    monkeypatch.setattr("services.customer_reply_v2.orchestrator.evaluate_customer_safety", _unc)
    out = await run_customer_reply_v2_dm(
        tenant_id="t_unc",
        message="hello",
        detected_language="en",
        response_language="en",
        provider_sender_id="u_unc",
        scripted_retrieval=[{"final_plan": {"evidence_status": "insufficient_final", "selected_source_ids": []}}],
        fixture_answer={"reply_text": "Hi there", "grounding_status": "grounded"},
    )
    assert out.reply
    assert out.reason != "safety_block"


@pytest.mark.asyncio
async def test_dm_payload_includes_channel_and_history(v2_env):
    await publish_test_content("t_meta", _rich_sections())
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    now = time.time()
    injected = [
        {"role": "user", "content": "earlier", "timestamp": now - 300},
        {"role": "assistant", "content": "ok", "timestamp": now - 200},
    ]
    out = await run_customer_reply_v2_dm(
        tenant_id="t_meta",
        message="hello",
        detected_language="en",
        response_language="en",
        channel="facebook_dm",
        provider_sender_id="u_meta",
        conversation_id="conv1",
        message_id="mid-9",
        injected_history=injected,
        scripted_retrieval=[{"final_plan": {"evidence_status": "insufficient_final", "selected_source_ids": []}}],
        fixture_answer={"reply_text": "Hi", "grounding_status": "grounded"},
    )
    meta = out.metadata.get("channel_metadata") or {}
    assert meta.get("platform") == "facebook"
    assert meta.get("surface") == "dm"
    assert meta.get("is_public") is False
    assert out.metadata.get("history_window_minutes") == 90
    assert out.metadata.get("history_messages_loaded", 0) >= 2
    metering = out.metadata.get("metering") or {}
    assert metering.get("customer_turn_id")
    ops = [row["operation"] for row in metering.get("invocations") or []]
    assert "luna_retrieval" in ops
    assert any(op.startswith("tera_") for op in ops)


@pytest.mark.asyncio
async def test_tera_tools_telemetry_does_not_lie_about_medium(monkeypatch: pytest.MonkeyPatch):
    from services.customer_reply_v2 import answer_luna as al
    from services.model_policy import MODEL_CUSTOMER_TERRA

    captured: dict = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs):
                    captured.update(kwargs)
                    msg = MagicMock()
                    msg.content = '{"reply_text":"hi","grounding_status":"grounded"}'
                    msg.tool_calls = None
                    choice = MagicMock()
                    choice.message = msg
                    resp = MagicMock()
                    resp.choices = [choice]
                    resp.model = MODEL_CUSTOMER_TERRA
                    resp.usage = None
                    return resp

    monkeypatch.setattr("services.llm_core_service.client", _FakeClient)
    response = await al._default_llm(
        [{"role": "user", "content": "{}"}],
        tools=[{"type": "function", "function": {"name": "create_customer_request", "parameters": {}}}],
        channel="instagram_dm",
    )
    assert captured["reasoning_effort"] == "none"
    assert response._linas_requested_reasoning_effort == "medium"
    assert response._linas_effective_reasoning_effort == "none"


def test_v10_flag_rollback_restores_three_hour_window(monkeypatch):
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "false")
    monkeypatch.delenv("CUSTOMER_DM_CONTEXT_WINDOW_HOURS", raising=False)
    from services.customer_reply_v2.flags import dm_context_window_hours

    assert dm_context_window_hours() == 3.0
