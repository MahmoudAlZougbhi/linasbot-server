"""Default retrieve plan for Customer DM agentic turns. No separate planner call."""

from __future__ import annotations

from services.brain.contracts.enums import SourceFamily
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.brain.planner.heuristic import planner_customer_text

_RETRIEVE_FAMILIES: list[SourceFamily] = [
    "knowledge",
    "care",
    "faq",
    "hours",
    "services",
    "prices",
    "products",
    "branches",
]


def default_agentic_plan(message: str) -> PlannerPlan:
    """Search published CM together. Request actions are Terra tools, not plan tasks."""
    text = planner_customer_text(message)
    task = PlannerTask(
        id="t_info",
        type="information",
        span=TaskSpan(text=text, end=len(text)),
        source_families=list(_RETRIEVE_FAMILIES),
    )
    return PlannerPlan(tasks=[task], read_only=True)


def information_plan_for_comment(plan: PlannerPlan, message: str) -> PlannerPlan:
    """Public comments discuss the post; they are not catalog send_resource turns."""
    tasks = []
    for task in plan.tasks:
        if task.type != "resource_request":
            tasks.append(task)
            continue
        tasks.append(
            task.model_copy(
                update={
                    "type": "information",
                    "source_families": list(_RETRIEVE_FAMILIES),
                }
            )
        )
    if not tasks:
        return default_agentic_plan(message)
    read_only = all(
        task.type in {"information", "comparison", "hours", "acknowledgement", "draft_correction"} for task in tasks
    )
    return plan.model_copy(update={"tasks": tasks, "read_only": read_only})
