"""Contract acceptance slices: coverage, confirmation, comments, follow-up, chunks."""

from __future__ import annotations

import pytest

from services.cm.schemas import CommentRule, CommentsSection
from services.customer_ai.actions.confirm import confirmation_valid
from services.customer_ai.comment_normalize import normalize_comment_mode
from services.customer_ai.comments.pipeline import deterministic_comment_result, winning_comment_mode
from services.customer_ai.compiler.chunks import chunk_document, contextual_groups
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask
from services.customer_ai.coverage import coverage_ok, omitted_task_types
from services.customer_ai.evals.fixtures import knowledge_heavy_corpus, service_appointment_corpus
from services.customer_ai.retrieve.cards import cards_from_sections


def test_coverage_detects_planner_omission() -> None:
    plan = PlannerPlan(tasks=[PlannerTask(id="t1", type="information", source_families=["services"])])
    missing = omitted_task_types("بدي سعر الليزر وساعات الفرع", plan)
    assert "hours" in missing
    assert coverage_ok("بدي سعر الليزر وساعات الفرع", plan, {"t1": "answered"}) is False


def _answered_plan() -> tuple[str, PlannerPlan, dict[str, str]]:
    from services.customer_ai.planner.heuristic import plan_message

    original = "what is the laser price?"
    plan = plan_message(original)
    return original, plan, {task.id: "answered" for task in plan.tasks}


def test_coverage_requires_the_envelope_to_carry_the_answer() -> None:
    original, plan, dispositions = _answered_plan()
    assert coverage_ok(original, plan, dispositions, reply_text="Laser is 99 USD", decision="reply") is True
    # "answered" with nothing to send is a silent drop.
    assert coverage_ok(original, plan, dispositions, reply_text="", decision="reply") is False
    assert coverage_ok(original, plan, dispositions, reply_text="   ", decision="reply") is False


def test_coverage_rejects_answered_dispositions_on_a_non_answer_decision() -> None:
    original, plan, dispositions = _answered_plan()
    assert coverage_ok(original, plan, dispositions, reply_text="What service?", decision="clarify") is False
    assert coverage_ok(original, plan, dispositions, reply_text="", decision="no_reply") is False


def test_coverage_rejects_empty_content_decisions() -> None:
    from services.customer_ai.coverage import delivery_ok

    assert delivery_ok({"t1": "pending_delivery"}, reply_text="", decision="clarify") is False
    assert delivery_ok({"t1": "pending_delivery"}, reply_text="", decision="no_reply") is False
    assert delivery_ok({"t1": "pending_delivery"}, reply_text="Sending it now", decision="reply") is True
    # Dispositions that never owed the customer text stay valid without a decision.
    assert delivery_ok({"t1": "policy_suppressed"}, reply_text="", decision="") is True


def test_confirmation_tied_to_revision() -> None:
    assert (
        confirmation_valid(
            message_id="m1",
            customer_text="yes",
            expected_revision="draft-1",
            current_revision="draft-2",
        )
        is False
    )
    assert (
        confirmation_valid(
            message_id="m1",
            customer_text="yes",
            expected_revision="draft-1",
            current_revision="draft-1",
        )
        is True
    )
    assert (
        confirmation_valid(
            message_id="",
            customer_text="yes",
            expected_revision="draft-1",
            current_revision="draft-1",
        )
        is False
    )


def test_seven_comment_modes_normalize() -> None:
    assert normalize_comment_mode(action="ignore") == "ignore"
    assert normalize_comment_mode(action="reply_comment", rule_mode="deterministic") == "static_comment"
    assert normalize_comment_mode(action="reply_dm", rule_mode="deterministic") == "static_dm"
    assert normalize_comment_mode(action="reply_comment_and_dm", rule_mode="deterministic") == "static_both"
    assert normalize_comment_mode(action="reply_comment", rule_mode="ai_guidance") == "ai_comment"
    assert normalize_comment_mode(action="send_dm", rule_mode="ai_guidance") == "ai_dm"
    assert normalize_comment_mode(action="reply_comment_and_dm", rule_mode="ai_guidance") == "ai_both"


def test_ignore_comment_is_policy_suppressed(monkeypatch: pytest.MonkeyPatch) -> None:
    section = CommentsSection(
        rules=[CommentRule(id="ig", action="ignore", trigger_type="all_comments", keywords=[])]
    )
    monkeypatch.setattr(
        "services.customer_ai.comments.pipeline.load_published_comments_section",
        lambda _tid: section,
    )
    mode, decision = winning_comment_mode(tenant_id="t1", comment_text="price?")
    assert mode == "ignore"
    result = deterministic_comment_result(mode, decision)
    assert result is not None
    assert result.stop_reason == "policy_suppressed"
    assert result.envelope.dispositions["comment"] == "policy_suppressed"


def test_knowledge_chunks_keep_two_sections() -> None:
    body = "# Aftercare\nDo not wash for 24 hours.\n# Refunds\nRefunds are allowed within seven days."
    chunks = chunk_document(document_id="doc1", body=body)
    assert len(chunks) >= 2
    groups = contextual_groups(chunks)
    assert list(groups) == ["doc1"]
    assert len(groups["doc1"]) >= 2


def test_eval_fixtures_are_business_agnostic() -> None:
    clinic = cards_from_sections(service_appointment_corpus())
    knowledge = cards_from_sections(knowledge_heavy_corpus())
    assert any(card.source_family == "services" for card in clinic)
    assert any(card.item_id == "knowledge:policy" for card in knowledge)


@pytest.mark.asyncio
async def test_followup_does_not_fake_customer_text(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_dm(**kwargs):
        captured.update(kwargs)
        return type("Out", (), {"reply": "", "answer": None, "text": None})()

    monkeypatch.setattr("services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm", fake_dm)
    from services.smart_followup.generation import generate_followup_text

    text = await generate_followup_text(
        tenant_id="t1",
        channel="instagram_dm",
        connection_id="c1",
        conversation_id="conv",
        customer_sender_id="u1",
        goal="gentle_check_in",
    )
    assert text == ""
    assert captured["message"] == ""
    assert captured["followup_goal"] == "gentle_check_in"
