"""Bounded tool execution for one agentic turn."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.turn import CustomerTurn
from services.brain.facts.structured import facts_from_tool_data
from services.brain.tools.registry import execute_tool


async def maybe_tool_calls(
    turn: CustomerTurn,
    plan: PlannerPlan,
    message: str,
    *,
    budget: int,
    trace: list[dict[str, Any]],
    coverage: Mapping[str, str] | None = None,
    skip_tools: set[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str], int]:
    from services.brain.agent.tool_decide import propose_tools_dynamic

    blocked = skip_tools or set()
    receipts: list[str] = []
    tool_rows: list[dict[str, Any]] = []
    used = 0
    proposals = await propose_tools_dynamic(plan, message, coverage=coverage)
    for proposal in proposals:
        if used >= budget:
            trace.append({"step": "TOOL", "reason": "budget_exhausted", "tool_calls": used})
            break
        name = str(proposal.get("tool") or "")
        args = dict(proposal.get("args") or {})
        if not name or name in blocked:
            continue
        if name in {"check_setup_resources", "list_resources"}:
            extra_ids = list(turn.extra.get("evidence_source_ids") or [])
            if extra_ids and "source_ids" not in args:
                args["source_ids"] = extra_ids
        used += 1
        result = await execute_tool(name, args, turn)
        tool_rows.append(
            {
                "tool": name,
                "ok": result.get("ok"),
                "error": result.get("error"),
                "task_id": proposal.get("task_id"),
                "source": proposal.get("source"),
            }
        )
        trace.append(
            {
                "step": "TOOL",
                "tool": name,
                "ok": result.get("ok"),
                "task_id": proposal.get("task_id"),
                "source": proposal.get("source"),
            }
        )
        if result.get("receipt"):
            receipt = result["receipt"]
            receipts.append(
                f"{receipt.get('action_type')}:{receipt.get('state')}:{receipt.get('backend_id') or receipt.get('reason')}"
            )
        elif result.get("ok") and result.get("data") is not None:
            receipts.append(f"tool:{name}:ok")
            for fact in facts_from_tool_data(
                name, result.get("data"), tenant_id=turn.tenant_id, task_id=str(proposal.get("task_id") or "")
            ):
                receipts.append(f"fact:{fact.kind}:{fact.entity_id}:{fact.value}")
    return tool_rows, receipts, used


def skip_tools_for_turn(turn: CustomerTurn, extra: dict[str, Any] | None) -> set[str]:
    skip: set[str] = set()
    if str(getattr(turn, "surface", "") or "") == "comment":
        skip.add("start_request")
    if (extra or {}).get("pending_human_escalate"):
        skip.add("escalate_to_human")
    return skip
