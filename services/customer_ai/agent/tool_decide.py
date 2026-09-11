"""Propose allowlisted Customer Brain tools from plan + optional LLM choice."""

from __future__ import annotations

import os
from typing import Any

from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.tools.registry import ACTION_TOOLS, READ_TOOLS, UNSUPPORTED_TOOLS


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
            name = "escalate_to_human"
        elif task.type == "resource_request":
            name = "resolve_resource"
        elif task.type in {"service_request", "product_request"}:
            name = "start_request"
        if not name or name in UNSUPPORTED_TOOLS:
            continue
        if name not in READ_TOOLS and name not in ACTION_TOOLS:
            continue
        out.append({"tool": name, "args": args, "task_id": task.id, "source": "plan"})
    return out


async def propose_tools_dynamic(plan: PlannerPlan, message: str, *, coverage: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Bounded dynamic tool proposals. Falls back to plan map if LLM unavailable."""
    base = propose_tools_from_plan(plan, message)
    missing = [tid for tid, state in (coverage or {}).items() if state in {"missing", "partial"}]
    if not missing or not (os.getenv("OPENAI_API_KEY") or "").strip():
        return base
    try:
        from services.customer_ai.providers.config import answer_model
        from services.llm_core_service import create_chat_completion

        allowed = sorted(READ_TOOLS | ACTION_TOOLS)
        response = await create_chat_completion(
            model=answer_model(),
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Pick up to 2 tools from this allowlist only. Reply as tool_name per line.\n"
                        f"Allowlist: {', '.join(allowed)}\n"
                        f"Missing tasks: {', '.join(missing)}\n"
                        f"Message: {message}"
                    ),
                }
            ],
            max_tokens=40,
        )
        text = str(response.choices[0].message.content or "")
        chosen: list[dict[str, Any]] = []
        for line in text.splitlines():
            name = line.strip().split()[0] if line.strip() else ""
            name = name.strip(",.`\"'")
            if name in UNSUPPORTED_TOOLS or (name not in READ_TOOLS and name not in ACTION_TOOLS):
                continue
            chosen.append(
                {
                    "tool": name,
                    "args": {"query": message, "task_id": missing[0] if missing else "dyn", "customer_text": message},
                    "task_id": missing[0] if missing else "dyn",
                    "source": "llm",
                }
            )
            if len(chosen) >= 2:
                break
        return base + chosen
    except Exception:
        return base
