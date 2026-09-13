"""Request-rule paraphrases must map to the published task type, not keywords only."""

from __future__ import annotations

from services.cm.request_rules import format_request_rules_for_ai
from services.customer_ai.evals.qa_tenants import linas_like_qa_sections, shop_b_qa_sections
from services.customer_ai.planner.heuristic import overlay_plan, plan_message


def test_appointment_paraphrases_are_service_request() -> None:
    messages = [
        "بدي موعد",
        "احجزلي",
        "فيني آخد appointment؟",
        "بدي جي لعندكن بكرا",
        "بدي book",
        "بدي اعمل ليزر الأسبوع الجاي",
        "I want an appointment",
        "Je veux prendre rendez-vous",
        "book me please",
    ]
    for message in messages:
        types = {task.type for task in plan_message(message).tasks}
        assert "service_request" in types, message


def test_product_paraphrases_are_product_request() -> None:
    messages = ["بدي اطلب المنتج", "اشتري After Care", "I want to buy the cream", "order this product"]
    for message in messages:
        types = {task.type for task in plan_message(message).tasks}
        assert "product_request" in types, message


def test_human_handoff_paraphrases_are_human_request() -> None:
    messages = [
        "بدي احكي مع حدا",
        "وصلني بموظف",
        "بدي مسؤول",
        "human please",
        "I want to speak to a person",
        "عندي شكوى",
    ]
    for message in messages:
        types = {task.type for task in plan_message(message).tasks}
        assert "human_request" in types, message


def test_hours_question_is_not_turned_into_booking() -> None:
    plan = plan_message("شو ساعات عمل فرع أنطلياس؟")
    types = {task.type for task in plan.tasks}
    assert "hours" in types
    assert "service_request" not in types


def test_overlay_keeps_hours_when_llm_only_sees_knowledge() -> None:
    from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

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
    assert any(task.type == "hours" for task in out.tasks)


def test_linas_qa_rules_block_is_not_shop_b() -> None:
    linas = format_request_rules_for_ai(linas_like_qa_sections()["requests_appointments"])
    other = format_request_rules_for_ai(shop_b_qa_sections()["requests_appointments"])
    assert "APPOINTMENT" in linas
    assert "HUMAN" in linas
    assert "Hamra" not in linas
    assert "APPOINTMENT" not in other
    assert "Hamra" in other
    assert "ليزر" not in other
