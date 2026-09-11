"""Typed evidence blocks for the final model. Search dumps are not instructions."""

from __future__ import annotations

from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.identity import IdentityBundle


def compose_evidence_context(
    *,
    identity: IdentityBundle | None,
    plan: PlannerPlan,
    bundle: EvidenceBundle,
    policy_notes: list[str] | None = None,
    receipts: list[str] | None = None,
    followup_goal: str = "",
) -> str:
    parts: list[str] = []
    if identity:
        parts.append(
            "IDENTITY\n"
            f"name={identity.assistant_name} business={identity.business_name}\n"
            f"tone={identity.tone} formality={identity.formality} length={identity.response_length}\n"
            f"do={'; '.join(identity.do_list)}\n"
            f"dont={'; '.join(identity.dont_list)}"
        )
        if identity.style_body:
            parts.append(f"STYLE\n{identity.style_body}")
    if followup_goal:
        from services.customer_ai.followup_goals import resolve_followup_instruction

        instruction = resolve_followup_instruction(followup_goal)
        block = f"FOLLOWUP_DUE\ngoal={followup_goal}\nThis is a system due event, not a new customer message."
        if instruction:
            block += f"\ninstruction={instruction}"
        parts.append(block)
    if policy_notes:
        parts.append("POLICY\n" + "\n".join(policy_notes))
    task_lines = [f"{task.id}:{task.type}:{','.join(task.source_families)}" for task in plan.tasks]
    parts.append("TASKS\n" + "\n".join(task_lines))
    ev_lines = [
        f"[{item.evidence_id}|{item.source_family}|rev={item.revision}]\n{item.title}\n{item.text}"
        for item in bundle.items
    ]
    parts.append("EVIDENCE\n" + ("\n\n".join(ev_lines) if ev_lines else "none"))
    if receipts:
        parts.append("RECEIPTS\n" + "\n".join(receipts))
    parts.append(
        "RULES\nUse only EVIDENCE and RECEIPTS for facts. Never invent prices, hours, stock, or booking success."
    )
    return "\n\n".join(parts)
