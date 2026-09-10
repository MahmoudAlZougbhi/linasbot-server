"""FAQ exact path and greeting inactivity mapping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.cm.schemas import DynamicMessageRecord, DynamicMessagesSection, FaqRecord, FaqSection, FaqVariant
from services.customer_ai.faq_exact import faq_fast_path_safe, find_exact_faq
from services.customer_ai.greeting import evaluate_greeting, inactivity_threshold
from services.customer_ai.history import build_history_snapshot


def test_faq_exact_sends_approved_answer_only() -> None:
    section = FaqSection(
        items=[
            FaqRecord(
                qa_group_id="faq1",
                status="active",
                variants=[FaqVariant(language="en", question="What are your hours?", answer="10-8 daily")],
            )
        ]
    )
    hit = find_exact_faq(section, "what are your hours?")
    assert hit is not None
    assert hit.answer == "10-8 daily"
    assert find_exact_faq(section, "what are your hours? and can I book") is None


def test_faq_does_not_swallow_human_or_second_question() -> None:
    assert faq_fast_path_safe("What are your hours?") is True
    assert faq_fast_path_safe("What are your hours? I want a human") is False
    assert faq_fast_path_safe("hours? and price?") is False


def test_draft_faq_is_not_served() -> None:
    section = FaqSection(
        items=[
            FaqRecord(
                qa_group_id="faq2",
                status="draft",
                variants=[FaqVariant(language="en", question="Price?", answer="20")],
            )
        ]
    )
    assert find_exact_faq(section, "Price?") is None


def test_greeting_uses_existing_12h_window(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "handlers.text_handlers_message_greeting.GREETING_INACTIVITY_SECONDS",
        43200,
    )
    assert inactivity_threshold() == timedelta(hours=12)


def test_greeting_session_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.customer_ai.greeting.load_dynamic_messages",
        lambda _tid: DynamicMessagesSection(
            items=[
                DynamicMessageRecord(
                    id="g1",
                    enabled=True,
                    trigger_mode="session_start",
                    en="Hello there",
                    ar="مرحبا",
                )
            ]
        ),
    )
    history = build_history_snapshot([{"id": "m1", "role": "user", "text": "hi"}], current_inbound_id="m1")
    decision = evaluate_greeting(
        tenant_id="t1",
        message="hi",
        history=history,
        language="en",
        now=datetime.now(UTC),
    )
    assert decision.eligible is True
    assert decision.text == "Hello there"
    follow = evaluate_greeting(
        tenant_id="t1",
        message="hi",
        history=history,
        invocation_kind="followup",
    )
    assert follow.eligible is False


@pytest.mark.asyncio
async def test_flag_on_exact_faq_is_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.faq_exact import FaqExactHit
    from services.customer_ai.gates import GateDecision
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    monkeypatch.setenv("CUSTOMER_BRAIN_ENABLED", "true")
    monkeypatch.setattr(
        "services.customer_ai.runtime.evaluate_gates",
        lambda turn, apply_credits=True, message="": GateDecision(True, "ok"),
    )
    monkeypatch.setattr(
        "services.customer_ai.turn_pipeline.find_published_exact_faq",
        lambda _tid, _msg: FaqExactHit("faq1", "en", "hours?", "We reply within one business day.", 1),
    )
    out = await run_customer_reply_v2_dm(tenant_id="t1", message="hours?")
    assert out.stop is False
    assert out.reply == "We reply within one business day."
    assert out.metadata.get("ai_called") is False
    assert out.metadata.get("path") == "faq_exact"
