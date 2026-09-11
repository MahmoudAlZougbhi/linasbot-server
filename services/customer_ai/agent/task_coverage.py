"""Per-task evidence coverage for multi-round retrieval."""

from __future__ import annotations

from typing import Any, Literal

from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.plan import PlannerPlan

TaskCoverageStatus = Literal["covered", "missing", "partial"]
CoverageState = TaskCoverageStatus

_INFO_TYPES = {"information", "hours", "comparison"}
_FAMILY_HINTS: dict[str, set[str]] = {
    "hours": {"hours", "branches"},
    "information": {"knowledge", "care", "faq", "services", "products", "prices", "branches"},
    "comparison": {"services", "products", "prices", "knowledge"},
}


def _task_families(task) -> set[str]:
    families = {str(f) for f in (task.source_families or []) if f and f != "none"}
    return families or set(_FAMILY_HINTS.get(task.type, set()))


def _facts_list(structured_facts: Any) -> list[dict[str, Any]]:
    if structured_facts is None:
        return []
    if isinstance(structured_facts, list):
        return [row for row in structured_facts if isinstance(row, dict)]
    if isinstance(structured_facts, dict):
        rows: list[dict[str, Any]] = []
        for key, value in structured_facts.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        rows.append({"family": key, **item})
                    else:
                        rows.append({"family": key, "value": item})
            elif value:
                rows.append({"family": key, "value": value})
        return rows
    return []


def evaluate_task_coverage(
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    structured_facts: Any = None,
) -> dict[str, TaskCoverageStatus]:
    """Map each plan task_id to covered|missing|partial."""
    facts = _facts_list(structured_facts)
    text = "\n".join(f"{item.title}\n{item.text}" for item in bundle.items).lower()
    families = {item.source_family for item in bundle.items}
    out: dict[str, TaskCoverageStatus] = {}
    for task in plan.tasks:
        if task.type not in _INFO_TYPES:
            out[task.id] = "covered"
            continue
        wanted = _task_families(task)
        fact_hit = any(
            str(fact.get("task_id") or "") == task.id or str(fact.get("family") or "") in wanted for fact in facts
        )
        family_hit = bool(wanted & families) or (not wanted and bool(bundle.items))
        tagged = any(task.id in (item.task_ids or []) for item in bundle.items)
        span = (task.span.text or "").strip().lower()
        token_hit = bool(span) and any(token and token in text for token in span.split()[:4])
        if tagged or fact_hit or (family_hit and (token_hit or not span)):
            out[task.id] = "covered"
        elif family_hit or token_hit:
            out[task.id] = "partial"
        else:
            out[task.id] = "missing"
    return out


def missing_tasks(plan: PlannerPlan, coverage: dict[str, TaskCoverageStatus]) -> list[str]:
    return [
        task.id
        for task in plan.tasks
        if task.type in _INFO_TYPES and coverage.get(task.id) in {"missing", "partial"}
    ]


def info_tasks_covered(plan: PlannerPlan, coverage: dict[str, TaskCoverageStatus]) -> bool:
    for task in plan.tasks:
        if task.type in _INFO_TYPES and coverage.get(task.id) != "covered":
            return False
    return True


def coverage_sufficient(coverage: dict[str, TaskCoverageStatus]) -> bool:
    return all(state == "covered" for state in coverage.values())
