"""Request-rule paraphrases: GPT planner is SoT; overlay only binds published types."""

from __future__ import annotations

from services.ai_setup.request_rules import format_request_rules_for_ai
from services.brain.planner.heuristic import overlay_plan, plan_message
from tests.brain_evals.qa_tenants import shop_a_qa_sections, shop_b_qa_sections
from tests.plan_builders import explicit_plan


def test_heuristic_paraphrases_are_fail_soft_information() -> None:
    for message in (
        "بدي موعد",
        "بدي اطلب المنتج",
        "بدي احكي مع حدا",
        "شو ساعات عمل فرع أنطلياس؟",
    ):
        assert {task.type for task in plan_message(message).tasks} == {"information"}


def test_hours_question_is_not_turned_into_booking() -> None:
    plan = explicit_plan("شو ساعات عمل فرع أنطلياس؟", ("hours", ["hours", "branches"]))
    types = {task.type for task in plan.tasks}
    assert "hours" in types
    assert "service_request" not in types


def test_overlay_keeps_llm_hours_plan() -> None:
    from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

    llm = PlannerPlan(
        tasks=[
            PlannerTask(
                id="t1",
                type="hours",
                span=TaskSpan(text="امتى بيفتح فرع أنطلياس؟"),
                source_families=["hours", "branches"],
            )
        ],
        read_only=True,
    )
    out = overlay_plan(llm, "امتى بيفتح فرع أنطلياس؟")
    assert any(task.type == "hours" for task in out.tasks)


def test_overlay_does_not_invent_hours_from_knowledge() -> None:
    from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

    llm = PlannerPlan(
        tasks=[
            PlannerTask(
                id="t1",
                type="information",
                span=TaskSpan(text="امتى بيفتح فرع أنطلياس؟"),
                source_families=["knowledge"],
            )
        ],
        read_only=True,
    )
    out = overlay_plan(llm, "امتى بيفتح فرع أنطلياس؟")
    assert all(task.type != "hours" for task in out.tasks)


def test_linas_qa_rules_block_is_not_shop_b() -> None:
    linas = format_request_rules_for_ai(shop_a_qa_sections()["requests_appointments"])
    other = format_request_rules_for_ai(shop_b_qa_sections()["requests_appointments"])
    assert "APPOINTMENT" in linas
    assert "HUMAN" in linas
    assert "Hamra" not in linas
    assert "APPOINTMENT" not in other
    assert "Hamra" in other
    assert "ليزر" not in other
