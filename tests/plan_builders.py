"""Explicit PlannerPlan builders. Live task types come from OpenAI, not heuristic regex."""

from __future__ import annotations

from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

_READ_ONLY = {"information", "comparison", "hours", "acknowledgement", "draft_correction"}


def explicit_plan(message: str, *typed: tuple[str, list[str]]) -> PlannerPlan:
    text = message or ""
    tasks = [
        PlannerTask(
            id=f"t{index}",
            type=task_type,  # type: ignore[arg-type]
            span=TaskSpan(text=text, end=len(text)),
            source_families=list(families),  # type: ignore[arg-type]
        )
        for index, (task_type, families) in enumerate(typed, start=1)
    ]
    read_only = all(task.type in _READ_ONLY for task in tasks)
    return PlannerPlan(tasks=tasks, read_only=read_only)
