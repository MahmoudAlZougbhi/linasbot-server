"""Public comment ORDER/APPOINTMENT: Terra invites DM. System never sends a template."""

from __future__ import annotations

from services.brain.contracts.plan import PlannerPlan
from services.brain.contracts.reply import OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn

_REQUEST_TYPES = {"product_request", "service_request"}
_INFO_TYPES = {"information", "comparison", "hours", "acknowledgement", "draft_correction"}


def is_comment_surface(turn: CustomerTurn) -> bool:
    return str(getattr(turn, "surface", "") or "") == "comment"


def comment_has_public_request(turn: CustomerTurn, plan: PlannerPlan) -> bool:
    return is_comment_surface(turn) and any(task.type in _REQUEST_TYPES for task in plan.tasks)


def skip_comment_request_staging(turn: CustomerTurn) -> bool:
    return is_comment_surface(turn)


def comment_request_policy_notes(turn: CustomerTurn, plan: PlannerPlan) -> list[str]:
    if not comment_has_public_request(turn, plan):
        return []
    mode = str((turn.extra or {}).get("comment_mode") or "").strip()
    channel = str(turn.channel or "").lower()
    notes = [
        "Public comment cannot complete an order or appointment. Do not persist a request. "
        "Do not claim it was submitted. Do not invent prices, times, or availability. "
        "In your own words, invite the customer to continue in DM so you can finish together. "
        "Do not collect phone, address, or other PII on the public comment."
    ]
    if "tiktok" in channel:
        notes.append("This is TikTok: write a public comment only. Never claim a private message was sent.")
    elif mode == "ai_comment":
        notes.append("Write a public comment that invites the customer to DM to finish the order or booking.")
    elif mode == "ai_dm":
        notes.append("Write the DM that continues the order or booking. Do not claim a public request was filed.")
    elif mode == "ai_both":
        notes.append(
            "Prefer a DM that continues the order or booking, plus an optional short public ack. "
            "Do not claim a private message was sent unless the DM text is actually being sent."
        )
    else:
        notes.append("Invite the customer to DM to finish the order or booking together.")
    return notes


def information_plan_for_comment(plan: PlannerPlan, message: str) -> PlannerPlan:
    """Public comments discuss the post; they are not catalog send_resource turns."""
    tasks = []
    for task in plan.tasks:
        if task.type != "resource_request":
            tasks.append(task)
            continue
        tasks.append(
            task.model_copy(
                update={
                    "type": "information",
                    "source_families": ["knowledge", "care", "services", "faq", "branches", "prices"],
                }
            )
        )
    if not tasks:
        from services.brain.planner.heuristic import fail_soft_plan

        return fail_soft_plan(message)
    read_only = all(task.type in _INFO_TYPES for task in tasks)
    return plan.model_copy(update={"tasks": tasks, "read_only": read_only})


def force_tiktok_public_messages(result: TurnResult, channel: str) -> TurnResult:
    if "tiktok" not in str(channel or "").lower():
        return result
    if not result.envelope.messages:
        return result
    seen: set[str] = set()
    messages: list[OutboundMessage] = []
    for item in result.envelope.messages:
        text = (item.text or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        messages.append(item.model_copy(update={"destination": "comment", "depends_on": []}))
    if messages == list(result.envelope.messages):
        return result
    extra = dict(result.extra)
    extra["tiktok_public_only"] = True
    return result.model_copy(
        update={"envelope": result.envelope.model_copy(update={"messages": messages}), "extra": extra}
    )
