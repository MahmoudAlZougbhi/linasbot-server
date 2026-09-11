"""Connect planner resource_request tasks to authorized send_resource receipts."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.plan import PlannerPlan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn


def _destination(channel: str) -> str:
    return "web_chat" if "web" in (channel or "") else "dm"


def _tokens(text: str) -> list[str]:
    return [
        part for part in "".join(ch if ch.isalnum() else " " for ch in (text or "").lower()).split() if len(part) > 2
    ]


def match_resource_refs(
    tenant_id: str,
    query: str,
    *,
    evidence_source_ids: list[str] | None = None,
    limit: int = 3,
) -> list[str]:
    """Pick published resource refs by title/description and optional evidence source ids."""
    from services.cm.setup_resources import index_published_resources

    try:
        index = index_published_resources(tenant_id)
    except Exception:
        return []
    wanted = set(evidence_source_ids or [])
    tokens = _tokens(query)
    scored: list[tuple[int, str]] = []
    for ref, record in index.items():
        blob = f"{record.get('title') or ''} {record.get('description') or ''}".lower()
        score = 0
        source_id = str(record.get("source_item_id") or "")
        if wanted and source_id in wanted:
            score += 10
        if wanted and any(source_id.endswith(f":{sid}") or sid in source_id for sid in wanted):
            score += 4
        score += sum(1 for token in tokens if token in blob)
        kind = str(record.get("resource_type") or "")
        if any(token in {"photo", "picture", "image", "video", "link"} for token in tokens) and kind in {
            "image",
            "video",
            "link",
            "file",
        }:
            score += 2
        if score > 0:
            scored.append((score, ref))
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [ref for _score, ref in scored[: max(1, limit)]]


def resource_proposals(
    plan: PlannerPlan,
    *,
    tenant_id: str,
    query: str,
    evidence_source_ids: list[str] | None = None,
) -> ActionProposalSet:
    refs = match_resource_refs(tenant_id, query, evidence_source_ids=evidence_source_ids)
    actions: list[ActionProposal] = []
    for task in plan.tasks:
        if task.type != "resource_request":
            continue
        target = refs[0] if refs else ""
        actions.append(
            ActionProposal(
                task_id=task.id,
                action_type="send_resource",
                target_id=target,
                fields={"resource_ref": target, "allowed_source_ids": list(evidence_source_ids or [])},
            )
        )
        if refs:
            refs = refs[1:] or refs[:1]
    return ActionProposalSet(actions=actions)


async def execute_resource_proposals(
    turn: CustomerTurn,
    proposals: ActionProposalSet,
    *,
    customer_text: str,
) -> list[dict[str, Any]]:
    from services.customer_ai.actions.execute import execute_actions

    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

        try:
            with whatsapp_session(require=False) as session:
                receipts = await execute_actions(
                    turn=turn,
                    proposals=proposals,
                    customer_text=customer_text,
                    session=session,
                )
        except WhatsAppDatabaseUnavailable:
            receipts = await execute_actions(turn=turn, proposals=proposals, customer_text=customer_text)
    except Exception:
        receipts = await execute_actions(turn=turn, proposals=proposals, customer_text=customer_text)
    return [item.model_dump() for item in receipts.receipts]


async def resource_request_result(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    plan: PlannerPlan,
    evidence_source_ids: list[str] | None = None,
) -> TurnResult | None:
    """Run send_resource for resource_request tasks. Returns None when no resource task."""
    if not any(task.type == "resource_request" for task in plan.tasks):
        return None
    proposals = resource_proposals(
        plan,
        tenant_id=turn.tenant_id,
        query=message,
        evidence_source_ids=evidence_source_ids,
    )
    if not proposals.actions:
        return None
    if not any(item.target_id for item in proposals.actions):
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="clarify",
                messages=[
                    OutboundMessage(
                        destination=_destination(channel),
                        text="I could not find an authorized photo or link for that yet.",
                        protected=True,
                    )
                ],
                dispositions={task.id: "not_found" for task in plan.tasks if task.type == "resource_request"},
            ),
            extra={"phase": "resource", "plan": plan.model_dump(), "receipts": []},
        )
    receipts = await execute_resource_proposals(turn, proposals, customer_text=message)
    ok = any(item.get("state") in {"pending", "success"} for item in receipts)
    text = (
        "I found the authorized media and queued it for delivery."
        if ok
        else "I could not send that media from the published catalog."
    )
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="deterministic" if ok else "clarify",
            messages=[OutboundMessage(destination=_destination(channel), text=text, protected=True)],
            dispositions={
                task.id: ("pending_delivery" if ok else "not_found")
                for task in plan.tasks
                if task.type == "resource_request"
            },
        ),
        extra={"phase": "resource", "plan": plan.model_dump(), "receipts": receipts},
    )
