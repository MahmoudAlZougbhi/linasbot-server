"""Hours/branch grounding: index weekly_schedule, overlay planner, coverage."""

from __future__ import annotations

from services.brain.agent.task_coverage import evaluate_task_coverage
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.planner.heuristic import overlay_plan, plan_message
from services.brain.retrieve.cards import cards_from_sections
from services.brain.retrieve.hydrate import expand_hits
from services.brain.retrieve.lexical import LexicalHit


def _week(open_t: str, close_t: str, *, sunday_off: bool = True) -> dict:
    day = {"enabled": True, "open": open_t, "close": close_t, "off_day": False}
    off = {"enabled": True, "open": "", "close": "", "off_day": True}
    week = {name: dict(day) for name in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday")}
    week["sunday"] = dict(off) if sunday_off else dict(day)
    return week


def test_branch_comparison_uses_hours_families() -> None:
    plan = plan_message("شو الفرق بين فرع بيروت وأنطلياس؟")
    cmp_tasks = [task for task in plan.tasks if task.type == "comparison"]
    assert cmp_tasks
    assert set(cmp_tasks[0].source_families) == {"hours", "branches"}


def test_antelias_hours_question_is_hours_task() -> None:
    plan = plan_message("شو ساعات أنطلياس؟")
    assert any(task.type == "hours" for task in plan.tasks)
    families = {fam for task in plan.tasks if task.type == "hours" for fam in task.source_families}
    assert families == {"hours", "branches"}
    assert "knowledge" not in families


def test_overlay_converts_knowledge_information_to_hours() -> None:
    llm = PlannerPlan(
        tasks=[
            PlannerTask(
                id="t1",
                type="information",
                span=TaskSpan(text="شو ساعات أنطلياس؟"),
                source_families=["knowledge", "care", "faq"],
            )
        ],
        read_only=True,
    )
    out = overlay_plan(llm, "شو ساعات أنطلياس؟")
    hours = [task for task in out.tasks if task.type == "hours"]
    assert hours
    assert "hours" in hours[0].source_families
    assert "branches" in hours[0].source_families
    assert "knowledge" not in hours[0].source_families


def test_multi_question_keeps_hours_family() -> None:
    plan = plan_message("What is the price? What are the hours?")
    types = {task.type for task in plan.tasks}
    assert "hours" in types
    assert any(task.type == "information" for task in plan.tasks)


def test_weekly_schedule_is_indexed_and_hydrated() -> None:
    sections = {
        "branches": {
            "items": [
                {
                    "id": "antelias",
                    "labels": {"en": "Antelias", "ar": "أنطلياس"},
                    "weekly_schedule": _week("11:00", "19:00"),
                },
                {
                    "id": "beirut",
                    "labels": {"en": "Beirut", "ar": "بيروت"},
                    "weekly_schedule": _week("10:00", "20:00"),
                },
            ]
        }
    }
    cards = cards_from_sections(sections)
    hours = [card for card in cards if card.source_family == "hours"]
    assert len(hours) == 2
    antelias = next(card for card in hours if "antelias" in card.item_id)
    assert "11 00" in antelias.search_text
    assert "19 00" in antelias.search_text
    bundle = expand_hits([LexicalHit(card=antelias, score=1.0)], sections)
    text = bundle.items[0].text
    assert "11:00" in text
    assert "19:00" in text
    assert "sunday: closed" in text


def test_hours_coverage_ignores_greeting_knowledge() -> None:
    plan = PlannerPlan(
        tasks=[
            PlannerTask(
                id="t_hours",
                type="hours",
                span=TaskSpan(text="antelias hours"),
                source_families=["hours", "branches"],
            )
        ]
    )
    greeting = EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="knowledge:greet",
                source_family="knowledge",
                source_id="greet",
                title="Greeting",
                text="Use this rule only if the user message is only a casual greeting. Antelias team.",
            )
        ],
        outcome="found",
    )
    coverage = evaluate_task_coverage(plan, greeting, {})
    assert coverage["t_hours"] == "missing"
    hours = EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="hours:antelias",
                source_family="hours",
                source_id="antelias",
                title="Antelias",
                text="Antelias monday: 11:00–19:00",
            )
        ],
        outcome="found",
    )
    covered = evaluate_task_coverage(plan, hours, {"hours": [{"id": "antelias", "task_id": "t_hours"}]})
    assert covered["t_hours"] == "covered"


def test_opening_hours_do_not_hide_branch_clocks() -> None:
    sections = {
        "opening_hours": {"items": [{"id": "oh_antelias", "title": "Antelias Opening Hours", "status": "active"}]},
        "branches": {
            "items": [
                {
                    "id": "antelias",
                    "title": "Antelias",
                    "aliases": ["أنطلياس"],
                    "weekly_schedule": _week("11:00", "19:00"),
                }
            ]
        },
        "knowledge": {
            "items": [
                {
                    "id": "greet",
                    "title": "Greeting policy",
                    "body": "Use this rule only if the user message is only a casual greeting. Antelias team.",
                    "status": "active",
                }
            ]
        },
    }
    cards = cards_from_sections(sections)
    hours_ids = {card.item_id for card in cards if card.source_family == "hours"}
    assert "hours:antelias" in hours_ids
    antelias = next(card for card in cards if card.item_id == "hours:antelias")
    assert "11 00" in antelias.search_text
    from services.brain.retrieve.lexical import search_cards

    hits = search_cards(cards, "شو ساعات أنطلياس؟", families={"hours", "branches"})
    assert hits
    assert hits[0].card.source_family in {"hours", "branches"}
    assert hits[0].card.source_family != "knowledge"


def test_two_tenants_do_not_share_hours_cards() -> None:
    linas = {
        "branches": {"items": [{"id": "antelias", "title": "Antelias", "weekly_schedule": _week("11:00", "19:00")}]}
    }
    other = {"branches": {"items": [{"id": "hamra", "title": "Hamra", "weekly_schedule": _week("09:00", "15:00")}]}}
    linas_ids = {card.item_id for card in cards_from_sections(linas, tenant_id="linas")}
    other_ids = {card.item_id for card in cards_from_sections(other, tenant_id="shop-b")}
    assert "hours:antelias" in linas_ids
    assert "hours:hamra" in other_ids
    assert "hours:hamra" not in linas_ids
    assert "hours:antelias" not in other_ids


def test_no_day_off_is_not_invented() -> None:
    sections = {
        "branches": {
            "items": [
                {
                    "id": "antelias",
                    "title": "Antelias",
                    "weekly_schedule": _week("11:00", "19:00", sunday_off=False),
                }
            ]
        },
        "off_days": {"rules": [], "notes": ""},
    }
    cards = cards_from_sections(sections)
    hours = next(card for card in cards if card.item_id == "hours:antelias")
    assert "closed" not in hours.search_text
    assert "no weekly off day" in hours.search_text
    assert not any(card.item_id == "hours:off_days" for card in cards)
    plan = plan_message("عندكن يوم عطلة؟")
    assert any(task.type == "hours" for task in plan.tasks)


def test_published_off_day_is_indexed() -> None:
    sections = {
        "branches": {
            "items": [{"id": "hamra", "title": "Hamra", "weekly_schedule": _week("09:00", "15:00", sunday_off=True)}]
        },
        "off_days": {"rules": [{"kind": "weekly", "weekday": 6, "reason": "Sunday closed"}]},
    }
    cards = cards_from_sections(sections)
    hours = next(card for card in cards if card.item_id == "hours:hamra")
    assert "sunday: closed" in " ".join(hours.search_text.split()) or "closed" in hours.search_text
    assert any(card.item_id == "hours:off_days" for card in cards)


def test_hydrate_clocks_when_branch_schedule_empty() -> None:
    """Production-shaped: clocks live on opening_hours, branch weekly_schedule is empty."""
    sections = {
        "opening_hours": {
            "items": [
                {
                    "id": "oh_antelias",
                    "title": "Antelias Opening Hours",
                    "aliases": ["antelias", "أنطلياس"],
                    "branch_id": "antelias",
                    "weekly_schedule": _week("11:00", "19:00", sunday_off=False),
                    "status": "active",
                }
            ]
        },
        "branches": {
            "items": [
                {
                    "id": "antelias",
                    "title": "Antelias",
                    "aliases": ["أنطلياس"],
                    "weekly_schedule": {},
                    "status": "active",
                }
            ]
        },
    }
    cards = cards_from_sections(sections)
    hours = next(card for card in cards if card.item_id == "hours:antelias")
    hydrated = expand_hits([LexicalHit(card=hours, score=1.0)], sections)
    assert hydrated.items
    text = hydrated.items[0].text.lower()
    assert "11:00" in hydrated.items[0].text
    assert "19:00" in hydrated.items[0].text
    assert "sunday: closed" not in text
    branch = next(card for card in cards if card.item_id == "branches:antelias")
    branch_text = expand_hits([LexicalHit(card=branch, score=1.0)], sections).items[0].text
    assert "11:00" in branch_text
    assert "19:00" in branch_text


def _hours_plan() -> PlannerPlan:
    return PlannerPlan(
        tasks=[
            PlannerTask(
                id="t_hours",
                type="hours",
                span=TaskSpan(text="antelias hours"),
                source_families=["hours", "branches"],
            )
        ]
    )


def _hours_card_without_clocks() -> EvidenceBundle:
    return EvidenceBundle(
        items=[
            EvidenceItem(
                evidence_id="hours:antelias",
                source_family="hours",
                source_id="antelias",
                title="Antelias",
                text="Antelias",
            )
        ],
        outcome="found",
    )


def test_hours_coverage_uses_receipt_and_kind_clocks() -> None:
    plan = _hours_plan()
    hours = _hours_card_without_clocks()
    assert evaluate_task_coverage(plan, hours, {})["t_hours"] == "partial"
    assert evaluate_task_coverage(plan, hours, {}, receipts=["tool:get_product:ok"])["t_hours"] == "partial"
    receipts = evaluate_task_coverage(
        plan,
        hours,
        {},
        receipts=["fact:hours:antelias:monday: 11:00–19:00"],
    )
    assert receipts["t_hours"] == "covered"
    kind_facts = [{"kind": "hours", "value": "monday: 11:00–19:00", "entity_id": "antelias"}]
    assert evaluate_task_coverage(plan, hours, kind_facts)["t_hours"] == "covered"
    no_clock_facts = [{"kind": "hours", "value": "Antelias", "entity_id": "antelias"}]
    assert evaluate_task_coverage(plan, hours, no_clock_facts)["t_hours"] == "partial"
