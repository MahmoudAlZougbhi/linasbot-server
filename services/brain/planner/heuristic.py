"""Fail-soft planner fallback. OpenAI/GPT plans are authoritative — no regex overlays."""

from __future__ import annotations

import re

from services.brain.contracts.enums import SourceFamily, TaskType
from services.brain.contracts.plan import PlannerPlan, PlannerTask, TaskSpan

_ANNOTATION_PREFIXES = (
    "post_media_type=",
    "post_kind=",
    "post_visual=",
    "post_audio_transcript=",
    "post_media_url=",
    "post_caption=",
)
_ANNOTATION_INLINE = re.compile(
    r"(?:post_media_type|post_kind|post_visual|post_audio_transcript|post_media_url|post_caption)="
    r".*?(?=(?:\s(?:post_media_type|post_kind|post_visual|post_audio_transcript|post_media_url|post_caption)=)|$)",
    re.I,
)
_RULE_BOUND = {"human_request", "service_request", "product_request"}
_READ_ONLY = {"information", "comparison", "hours", "acknowledgement", "draft_correction"}
_FAIL_SOFT_FAMILIES: list[SourceFamily] = [
    "knowledge",
    "care",
    "services",
    "faq",
    "branches",
    "prices",
]


def planner_customer_text(message: str) -> str:
    """Drop Brain post-analysis tokens so they cannot fake a catalog photo request."""
    cleaned = _ANNOTATION_INLINE.sub(" ", message or "")
    kept: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(stripped.casefold().startswith(prefix) for prefix in _ANNOTATION_PREFIXES):
            continue
        kept.append(stripped)
    return "\n".join(kept).strip()


def _task(task_id: str, task_type: TaskType, text: str, families: list[SourceFamily]) -> PlannerTask:
    return PlannerTask(
        id=task_id,
        type=task_type,
        span=TaskSpan(text=text, end=len(text)),
        source_families=families,
    )


def fail_soft_plan(message: str) -> PlannerPlan:
    """Information-only plan when OpenAI is unavailable. Not a keyword catalog."""
    text = planner_customer_text(message)
    return PlannerPlan(tasks=[_task("t_info", "information", text, list(_FAIL_SOFT_FAMILIES))], read_only=True)


def plan_message(message: str) -> PlannerPlan:
    """Fail-soft information plan. Live request actions come from Terra tools, not this fallback."""
    return fail_soft_plan(message)


def _bind_request_rules(
    plan: PlannerPlan,
    message: str,
    enabled_action_types: set[str] | None,
) -> PlannerPlan:
    if enabled_action_types is None:
        return plan
    tasks = [task for task in plan.tasks if task.type not in _RULE_BOUND or task.type in enabled_action_types]
    if not tasks:
        tasks = [_task("t_info", "information", message, list(_FAIL_SOFT_FAMILIES))]
    read_only = all(task.type in _READ_ONLY for task in tasks)
    return plan.model_copy(update={"tasks": tasks, "read_only": read_only})


def overlay_plan(
    llm: PlannerPlan | None,
    message: str,
    *,
    enabled_action_types: set[str] | None = None,
) -> PlannerPlan:
    """Keep the GPT plan. Bind published tenant request rules. Never regex force-correct."""
    text = planner_customer_text(message)
    if llm is None or not llm.tasks:
        return _bind_request_rules(fail_soft_plan(text), text, enabled_action_types)
    return _bind_request_rules(llm, text, enabled_action_types)
