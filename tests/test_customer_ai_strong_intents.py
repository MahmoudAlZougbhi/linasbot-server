"""Strong multi-intent planner/retrieval contracts. No live provider spend."""

from __future__ import annotations

from services.customer_ai.evals.qa_tenants import linas_like_qa_sections, shop_b_qa_sections
from services.customer_ai.planner.heuristic import overlay_plan, plan_message
from services.customer_ai.retrieve.cards import cards_from_sections
from services.customer_ai.retrieve.expand import expand_hits
from services.customer_ai.retrieve.lexical import LexicalHit, search_cards


def test_multi_intent_keeps_hours_price_booking_and_photo() -> None:
    message = "بدي سعر الليزر ببيروت وساعات أنطلياس وصورة الليزر وإذا في مجال موعد بكرا وقارنلي بين فرع بيروت وأنطلياس"
    types = {task.type for task in plan_message(message).tasks}
    assert {"hours", "information", "service_request", "resource_request", "comparison"} <= types


def test_handoff_and_price_and_hours_stay_separate() -> None:
    message = "هيدا الفرع امتى بيفتح وشو سعر الفول بودي وفرجيني صورته وبدي احكي مع حدا إذا السعر غالي"
    types = {task.type for task in plan_message(message).tasks}
    assert "human_request" in types
    assert "hours" in types
    assert "resource_request" in types


def test_overlay_keeps_actions_when_llm_drops_them() -> None:
    from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

    llm = PlannerPlan(
        tasks=[
            PlannerTask(
                id="t1",
                type="information",
                span=TaskSpan(text="بدي موعد وصوره وموظف"),
                source_families=["knowledge"],
            )
        ]
    )
    out = overlay_plan(llm, "بدي موعد وفرجيني صورة الليزر وبدي احكي مع حدا")
    types = {task.type for task in out.tasks}
    assert "service_request" in types
    assert "resource_request" in types
    assert "human_request" in types


def test_linas_qa_laser_photo_stays_on_linas() -> None:
    linas = cards_from_sections(linas_like_qa_sections(), tenant_id="qa-linas")
    other = cards_from_sections(shop_b_qa_sections(), tenant_id="qa-shop-b")
    linas_blob = " ".join(card.search_text for card in linas)
    other_blob = " ".join(card.search_text for card in other)
    assert "qa.linas.example/laser-women.png" in linas_blob or "laser women" in linas_blob
    assert "qa.linas.example" not in other_blob
    assert "antelias" not in other_blob


def test_linas_qa_has_no_closed_sunday() -> None:
    cards = cards_from_sections(linas_like_qa_sections(), tenant_id="qa-linas")
    antelias = next(card for card in cards if "antelias" in card.item_id and card.source_family == "hours")
    assert "closed" not in antelias.search_text
    hamra = [
        card
        for card in cards_from_sections(shop_b_qa_sections(), tenant_id="qa-shop-b")
        if card.source_family == "hours"
    ]
    assert hamra
    assert any("closed" in card.search_text for card in hamra)


def test_hours_query_does_not_rank_greeting_first() -> None:
    cards = cards_from_sections(linas_like_qa_sections(), tenant_id="qa-linas")
    hits = search_cards(cards, "امتى بيفتح فرع أنطلياس؟", families={"hours", "branches"})
    assert hits
    assert hits[0].card.source_family in {"hours", "branches"}
    bundle = expand_hits([LexicalHit(card=hits[0].card, score=1.0)], linas_like_qa_sections(), tenant_id="qa-linas")
    text = bundle.items[0].text
    assert "11:00" in text
    assert "greeting" not in text.lower()
