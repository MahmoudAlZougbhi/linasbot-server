"""Propose allowlisted Customer Brain tools from the retrieve plan map. No LLM."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.brain.contracts.plan import PlannerPlan
from services.brain.tools.registry import ACTION_TOOLS, READ_TOOLS, UNSUPPORTED_TOOLS


def propose_tools_from_plan(plan: PlannerPlan, message: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for task in plan.tasks:
        name = ""
        args: dict[str, Any] = {
            "query": task.span.text or message,
            "task_id": task.id,
            "customer_text": message,
        }
        if task.type == "hours":
            name = "get_branch_hours"
        elif task.type == "information" and any(f in {"prices", "services"} for f in task.source_families):
            name = "get_price"
        elif task.type == "information" and "products" in task.source_families:
            name = "search_products"
        elif task.type == "human_request":
            continue
        elif task.type == "resource_request":
            name = "check_setup_resources"
        elif task.type in {"service_request", "product_request"}:
            continue
        if not name or name in UNSUPPORTED_TOOLS:
            continue
        if name not in READ_TOOLS and name not in ACTION_TOOLS:
            continue
        out.append({"tool": name, "args": args, "task_id": task.id, "source": "plan"})
    return out


async def propose_tools_dynamic(
    plan: PlannerPlan, message: str, *, coverage: Mapping[str, str] | None = None
) -> list[dict[str, Any]]:
    """Plan-map only. Terra chooses tools in the single agent session."""
    _ = coverage
    return propose_tools_from_plan(plan, message)
