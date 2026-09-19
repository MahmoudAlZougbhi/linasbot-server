"""Freeze: keyword/regex catalogs must not gate Terra or Sol."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from services.brain.planner.heuristic import overlay_plan, plan_message
from services.brain.turn_pipeline import run_dm_after_gates
from services.owner_copilot.creative_policy import CANCELLED_CREATIVE_TOOLS

ROOT = Path(__file__).resolve().parents[1]
SCAN_DIRS = (
    ROOT / "services/brain",
    ROOT / "services/owner_copilot",
)
FORBIDDEN = (
    "BUSINESS_SCOPE_KEYWORDS",
    "OFF_TOPIC_KEYWORDS",
    "ALLOWED_GENERAL_QUERIES",
    "_is_out_of_business_scope_query",
    "out_of_scope_guard",
    "is_greeting_only",
    "GREETING_ONLY",
    "common_greetings_only",
    "CREATIVE_KEYWORDS",
    "looks_like_creative_request",
    "looks_like_owner_assent",
    "HUMAN_REQUEST_KEYWORDS",
    "ANGER_KEYWORDS",
    "OFFENSIVE_KEYWORDS",
    "_ACK_RE",
    "_PRICE_INTENT",
    "is_catalog_list",
    "is_human_request",
    "CLINIC_SCOPE_KEYWORDS",
)
VERTICAL = ("ليناز",)
FOUNDER_NAME = re.compile(r"(?<![\u0600-\u06FF])لينا(?![\u0600-\u06FF])")


def _py_files() -> list[Path]:
    files: list[Path] = []
    for folder in SCAN_DIRS:
        files.extend(path for path in folder.rglob("*.py") if "__pycache__" not in path.parts)
    return files


def test_constitution_files_exist() -> None:
    assert (ROOT / ".cursor/rules/linas-ai-constitution.mdc").is_file()
    assert (ROOT / "docs/LINAS_AI_CONSTITUTION.md").is_file()
    law = (ROOT / ".cursor/rules/linas-ai-constitution.mdc").read_text(encoding="utf-8")
    assert "ONLY allowed reason to withhold a message from the AI model" in law
    assert "FORBIDDEN forever to add keyword/regex gates" in law


def test_gating_lexicons_stay_gone() -> None:
    hits: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        for needle in FORBIDDEN:
            if needle in text:
                hits.append(f"{rel}:{needle}")
        if path.name == "heuristic.py" and "_HOURS = re.compile" in text:
            hits.append(f"{rel}:hours_regex_overlay")
        if "sentiment_keyword_analyzer" in text:
            hits.append(f"{rel}:sentiment_keyword_analyzer")
    assert not hits, hits


def test_no_founder_clinic_tokens_in_ai_paths() -> None:
    hits: list[str] = []
    for path in _py_files():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(ROOT))
        for needle in VERTICAL:
            if needle in text:
                hits.append(f"{rel}:{needle}")
        if FOUNDER_NAME.search(text):
            hits.append(f"{rel}:لينا")
    assert not hits, hits


def test_heuristic_is_fail_soft_not_keyword_plan() -> None:
    plan = plan_message("بدي احكي مع حدا")
    assert {task.type for task in plan.tasks} == {"information"}
    hours = plan_message("what are your opening hours?")
    assert {task.type for task in hours.tasks} == {"information"}
    greet = plan_message("مرحبا")
    assert {task.type for task in greet.tasks} == {"information"}


def test_overlay_does_not_force_correct_gpt() -> None:
    from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

    llm = PlannerPlan(
        tasks=[
            PlannerTask(
                id="t1",
                type="information",
                span=TaskSpan(text="شو ساعات أنطلياس؟"),
                source_families=["knowledge"],
            )
        ],
        read_only=True,
    )
    out = overlay_plan(llm, "شو ساعات أنطلياس؟")
    assert [task.type for task in out.tasks] == ["information"]
    assert out.tasks[0].source_families == ["knowledge"]


def test_phase2_has_no_out_of_scope_halt() -> None:
    src = (ROOT / "services/brain/inbound/text_handlers_respond_phase2.py").read_text(encoding="utf-8")
    assert "out_of_scope_guard" not in src
    assert "_is_out_of_business_scope_query" not in src
    assert "scope_guard" not in src


def test_turn_pipeline_does_not_regex_skip_greetings() -> None:
    src = (ROOT / "services/brain/turn_pipeline.py").read_text(encoding="utf-8")
    assert "is_greeting_only" not in src
    stream = (ROOT / "services/owner_copilot/brain_stream_body.py").read_text(encoding="utf-8")
    assert "looks_like_creative_request" not in stream
    assert "looks_like_owner_assent" not in stream


def test_cancelled_creative_tools_stay_registry_disabled() -> None:
    assert "create_creative_draft" in CANCELLED_CREATIVE_TOOLS
    from services.owner_copilot.tool_schemas import tool_names

    assert "create_creative_draft" not in tool_names()


@pytest.mark.asyncio
async def test_politics_style_inbound_reaches_terra_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
    from services.brain.contracts.turn import CustomerTurn

    called = {"agentic": False}

    async def agentic(*_a, **_k):
        called["agentic"] = True
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="terra-saw-it")],
            ),
            ai_called=True,
        )

    async def no_confirm(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", no_confirm)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", agentic)
    turn = CustomerTurn(tenant_id="t1", conversation_id="c-pol", extra={"response_language": "en"})
    out = await run_dm_after_gates(turn, message="who is the president?", channel="instagram_dm")
    assert called["agentic"] is True
    assert out.ai_called is True
    assert out.envelope.messages[0].text == "terra-saw-it"


@pytest.mark.asyncio
async def test_greeting_marhaba_runs_planner_or_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
    from services.brain.contracts.turn import CustomerTurn

    async def agentic(*_a, **_k):
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="instagram_dm", text="terra-greeting")],
            ),
            ai_called=True,
        )

    async def no_confirm(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline.try_confirm_pending", no_confirm)
    monkeypatch.setattr("services.brain.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_sem(*_a, **_k):
        return None

    monkeypatch.setattr("services.brain.turn_pipeline._semantic_faq_result", no_sem)
    monkeypatch.setattr("services.brain.agent.loop.run_agentic_dm_path", agentic)
    turn = CustomerTurn(tenant_id="t1", conversation_id="c-hi", extra={"response_language": "ar"})
    out = await run_dm_after_gates(turn, message="مرحبا", channel="instagram_dm")
    assert out.ai_called is True
    assert out.envelope.messages[0].text == "terra-greeting"


def test_opt_out_does_not_block_terra_inbound() -> None:
    message = (ROOT / "services/brain/inbound/text_handlers_message.py").read_text(encoding="utf-8")
    assert "looks_like_opt_out" in message
    assert "schedule_combined_turn" in message
    phase2 = (ROOT / "services/brain/inbound/text_handlers_respond_phase2.py").read_text(encoding="utf-8")
    assert "looks_like_opt_out" not in phase2
    assert "out_of_scope_guard" not in phase2
