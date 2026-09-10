"""Coverage: original message vs plan vs dispositions. Planner self-report is not enough."""

from __future__ import annotations

from services.customer_ai.contracts.enums import TaskDisposition, TaskType
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.planner.heuristic import plan_message

_DONE: set[TaskDisposition] = {
    "answered",
    "action_succeeded",
    "awaiting_customer",
    "pending_delivery",
    "policy_suppressed",
    "not_found",
    "blocked",
}


def omitted_task_types(original: str, plan: PlannerPlan) -> list[TaskType]:
    expected = plan_message(original)
    planned = {task.type for task in plan.tasks}
    missing: list[TaskType] = []
    for task in expected.tasks:
        if task.type == "acknowledgement":
            continue
        if task.type not in planned:
            missing.append(task.type)
    return missing


def uncovered_task_ids(plan: PlannerPlan, dispositions: dict[str, TaskDisposition]) -> list[str]:
    uncovered: list[str] = []
    for task in plan.tasks:
        status = dispositions.get(task.id)
        if status not in _DONE:
            uncovered.append(task.id)
    return uncovered


def coverage_ok(original: str, plan: PlannerPlan, dispositions: dict[str, TaskDisposition]) -> bool:
    return not omitted_task_types(original, plan) and not uncovered_task_ids(plan, dispositions)
