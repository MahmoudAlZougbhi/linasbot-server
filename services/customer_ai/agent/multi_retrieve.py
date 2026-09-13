"""Multi-round retrieval with early stop when plan tasks are covered."""

from __future__ import annotations

import asyncio
from typing import Any

from services.customer_ai.agent.normalize_query import normalize_query
from services.customer_ai.agent.rewrite import rewrite_queries
from services.customer_ai.agent.task_coverage import (
    evaluate_task_coverage,
    info_tasks_covered,
    missing_tasks,
)
from services.customer_ai.budgets import DEFAULT_BUDGETS
from services.customer_ai.contracts.enums import SourceFamily
from services.customer_ai.contracts.evidence import EvidenceBundle, EvidenceItem
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.retrieve.orchestrate import RetrieveContext, retrieve_published

_INFO_TYPES = {"information", "hours", "comparison"}


def _families(task: PlannerTask) -> set[SourceFamily] | None:
    cleaned: set[SourceFamily] = {item for item in (task.source_families or []) if item != "none"}
    return cleaned or None


def _merge_items(existing: list[EvidenceItem], incoming: list[EvidenceItem]) -> list[EvidenceItem]:
    by_id: dict[str, EvidenceItem] = {item.evidence_id: item for item in existing if item.evidence_id}
    order = [item.evidence_id for item in existing if item.evidence_id]
    for item in incoming:
        eid = item.evidence_id or f"{item.source_family}:{item.source_id}"
        if eid in by_id:
            prev = by_id[eid]
            task_ids = list(dict.fromkeys([*(prev.task_ids or []), *(item.task_ids or [])]))
            by_id[eid] = prev.model_copy(update={"task_ids": task_ids})
            continue
        by_id[eid] = item.model_copy(update={"evidence_id": eid})
        order.append(eid)
    return [by_id[eid] for eid in order if eid in by_id]


def _tag_task(bundle: EvidenceBundle, task_id: str) -> EvidenceBundle:
    items = [
        item.model_copy(update={"task_ids": list(dict.fromkeys([*(item.task_ids or []), task_id]))})
        for item in bundle.items
    ]
    return bundle.model_copy(update={"items": items})


def _task_query(
    *,
    task: PlannerTask,
    message: str,
    normalized: dict[str, Any],
    rewritten: dict[str, Any],
    variants: list[str],
    round_idx: int,
) -> tuple[str, set[SourceFamily] | None]:
    families = _families(task)
    if task.type == "hours":
        seed = (task.span.text or message).strip() or message
        lowered = seed.casefold()
        if "hour" not in lowered and "دوام" not in seed and "ساعات" not in seed:
            seed = f"{seed} hours دوام"
        return seed, families or {"hours", "branches"}
    parts = [
        normalized.get("primary") or message,
        rewritten.get("rewritten") or message,
        (task.span.text or "").strip(),
        *variants[:1],
    ]
    if round_idx > 1:
        parts.append(f"{task.span.text or task.type}")
    seen: set[str] = set()
    query_bits: list[str] = []
    for part in parts:
        key = (part or "").strip().casefold()
        if key and key not in seen:
            seen.add(key)
            query_bits.append(part.strip())
    return " ".join(query_bits[:3]) or message, _families(task)


def _fold_round_bundle(
    *,
    merged: list[EvidenceItem],
    outcome: str,
    tagged: EvidenceBundle,
) -> tuple[list[EvidenceItem], str]:
    merged = _merge_items(merged, list(tagged.items))
    if tagged.outcome == "found" or merged:
        return merged, "found"
    if outcome == "not_found" and tagged.outcome not in {"not_found", "found"}:
        return merged, str(tagged.outcome)
    return merged, outcome


async def _retrieve_round(
    turn: CustomerTurn,
    targets: list[PlannerTask],
    *,
    message: str,
    normalized: dict[str, Any],
    rewritten: dict[str, Any],
    variants: list[str],
    round_idx: int,
) -> list[tuple[PlannerTask, str, set[SourceFamily] | None, EvidenceBundle]]:
    planned = [
        (
            task,
            *_task_query(
                task=task,
                message=message,
                normalized=normalized,
                rewritten=rewritten,
                variants=variants,
                round_idx=round_idx,
            ),
        )
        for task in targets
    ]
    unique_jobs: list[tuple[tuple[str, tuple[str, ...]], str, set[SourceFamily] | None]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for _task, query, families in planned:
        key = (query, tuple(sorted(families or ())))
        if key in seen:
            continue
        seen.add(key)
        unique_jobs.append((key, query, families))
    bundles = await asyncio.gather(
        *[
            retrieve_published(RetrieveContext(tenant_id=turn.tenant_id, query=query, families=families))
            for _key, query, families in unique_jobs
        ]
    )
    by_key = {key: bundle for (key, _query, _families), bundle in zip(unique_jobs, bundles, strict=True)}
    out: list[tuple[PlannerTask, str, set[SourceFamily] | None, EvidenceBundle]] = []
    for task, query, families in planned:
        key = (query, tuple(sorted(families or ())))
        bundle = by_key[key]
        tagged = _tag_task(bundle, task.id) if bundle.items else bundle
        out.append((task, query, families, tagged))
    return out


def _structured_facts(bundle: EvidenceBundle) -> dict[str, Any]:
    facts: dict[str, list[dict[str, Any]]] = {
        "prices": [],
        "hours": [],
        "branches": [],
        "services": [],
        "products": [],
        "knowledge": [],
    }
    for item in bundle.items:
        row = {"id": item.source_id, "title": item.title, "text": item.text[:400], "task_ids": list(item.task_ids)}
        family = item.source_family
        if family in {"prices", "services"}:
            facts["prices"].append(row)
            facts["services"].append(row)
        elif family == "hours":
            facts["hours"].append(row)
        elif family == "branches":
            facts["branches"].append(row)
        elif family == "products":
            facts["products"].append(row)
        elif family in {"knowledge", "care", "faq"}:
            facts["knowledge"].append(row)
    return {key: value for key, value in facts.items() if value}


async def multi_round_retrieve(
    turn: CustomerTurn,
    plan: PlannerPlan,
    message: str,
    *,
    max_rounds: int | None = None,
) -> tuple[EvidenceBundle, list[dict[str, Any]], dict[str, Any]]:
    """Returns (EvidenceBundle, round_trace, structured_facts)."""
    rounds = max(1, int(max_rounds if max_rounds is not None else DEFAULT_BUDGETS.max_retrieval_rounds))
    history = list(turn.history.messages)
    language = str((turn.extra or {}).get("response_language") or "")
    rewritten = await rewrite_queries(message, history, language)
    normalized = normalize_query(rewritten.get("rewritten") or message)
    variants = list(rewritten.get("variants") or []) + list(normalized.get("alternates") or [])

    merged: list[EvidenceItem] = []
    outcome = "not_found"
    trace: list[dict[str, Any]] = []
    coverage: dict[str, Any] = {}
    facts: dict[str, Any] = {}

    info_tasks = [task for task in plan.tasks if task.type in _INFO_TYPES] or list(plan.tasks)

    for round_idx in range(1, rounds + 1):
        targets = info_tasks
        if round_idx > 1:
            missing_ids = set(missing_tasks(plan, coverage))  # type: ignore[arg-type]
            targets = [task for task in info_tasks if task.id in missing_ids]
            if not targets:
                break
        retrieved = await _retrieve_round(
            turn,
            targets,
            message=message,
            normalized=normalized,
            rewritten=rewritten,
            variants=variants,
            round_idx=round_idx,
        )
        for task, query, families, tagged in retrieved:
            merged, outcome = _fold_round_bundle(merged=merged, outcome=outcome, tagged=tagged)
            trace.append(
                {
                    "round": round_idx,
                    "query": query,
                    "families": sorted(families) if families else [],
                    "hit_ids": [item.evidence_id for item in tagged.items],
                    "task_id": task.id,
                    "reason": "initial" if round_idx == 1 else "missing_retry",
                    "outcome": tagged.outcome,
                }
            )
        provisional = EvidenceBundle(items=merged, outcome=outcome)  # type: ignore[arg-type]
        from services.customer_ai.retrieve.conflict import apply_authority

        provisional, conflict_meta = apply_authority(provisional)
        merged = list(provisional.items)
        facts = _structured_facts(provisional)
        coverage = evaluate_task_coverage(plan, provisional, facts)
        if conflict_meta.get("decisions"):
            trace.append(
                {
                    "round": round_idx,
                    "query": "",
                    "families": [],
                    "hit_ids": [],
                    "reason": "authority_conflict_resolved",
                    "decisions": conflict_meta.get("decisions"),
                }
            )
        if info_tasks_covered(plan, coverage):
            trace.append(
                {"round": round_idx, "query": "", "families": [], "hit_ids": [], "reason": "early_stop_covered"}
            )
            break

    return EvidenceBundle(items=merged, outcome=outcome if merged else outcome), trace, facts  # type: ignore[arg-type]
