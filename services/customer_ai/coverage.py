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


_CONTENT_DECISIONS: set[str] = {"reply", "deterministic", "clarify", "no_reply", "handoff_ack"}
_NOT_AN_ANSWER: set[str] = {"no_reply", "clarify"}


def delivery_ok(
    dispositions: dict[str, TaskDisposition],
    *,
    reply_text: str = "",
    decision: str = "",
) -> bool:
    """Dispositions are only credible when the envelope really carries the text.

    `answered` with nothing to send — or any decision that owes the customer content and has
    none — is a silent drop: the self-report says the customer was served and they were not.
    """
    text = (reply_text or "").strip()
    answered = any(status == "answered" for status in dispositions.values())
    if answered and decision in _NOT_AN_ANSWER:
        return False
    if text:
        return True
    if answered:
        return False
    return decision not in _CONTENT_DECISIONS


def coverage_ok(
    original: str,
    plan: PlannerPlan,
    dispositions: dict[str, TaskDisposition],
    *,
    reply_text: str = "",
    decision: str = "",
) -> bool:
    if omitted_task_types(original, plan) or uncovered_task_ids(plan, dispositions):
        return False
    return delivery_ok(dispositions, reply_text=reply_text, decision=decision)
