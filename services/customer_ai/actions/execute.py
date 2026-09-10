"""Validate and execute actions[]. Receipts are server-authored."""

from __future__ import annotations

from typing import Any

from services.customer_ai.actions.drafts import apply_draft_update, cancel_request_or_draft
from services.customer_ai.actions.handoff import escalate_to_human
from services.customer_ai.actions.requests import persist_request
from services.customer_ai.actions.resources import send_resource
from services.customer_ai.contracts.actions import ActionProposalSet, ActionReceipt, ActionReceiptSet
from services.customer_ai.contracts.turn import CustomerTurn


async def execute_actions(
    *,
    turn: CustomerTurn,
    proposals: ActionProposalSet,
    customer_text: str,
    session: Any | None = None,
) -> ActionReceiptSet:
    receipts: list[ActionReceipt] = []
    inbound = turn.history.included_inbound_ids[0] if turn.history.included_inbound_ids else ""
    for proposal in proposals.actions:
        if proposal.action_type == "no_op":
            receipts.append(
                ActionReceipt(action_id=f"noop:{proposal.task_id}", action_type="no_op", state="success")
            )
            continue
        if proposal.action_type == "escalate_to_human":
            receipts.append(
                await escalate_to_human(
                    proposal=proposal,
                    user_id=turn.customer_id,
                    conversation_id=turn.conversation_id,
                )
            )
            continue
        if proposal.action_type == "send_resource":
            receipts.append(send_resource(tenant_id=turn.tenant_id, proposal=proposal, session=session))
            continue
        if proposal.action_type == "update_draft":
            receipts.append(
                apply_draft_update(
                    proposal=proposal,
                    current_revision=turn.state.draft_revision,
                    previous_fields=dict(proposal.fields.get("previous_fields") or {}),
                    session=session,
                    tenant_id=turn.tenant_id,
                    actor_user_id=turn.customer_id or "customer_ai",
                )
            )
            continue
        if proposal.action_type == "cancel_request":
            receipts.append(
                cancel_request_or_draft(
                    proposal=proposal,
                    session=session,
                    tenant_id=turn.tenant_id,
                    actor_user_id=turn.customer_id or "customer_ai",
                )
            )
            continue
        if proposal.action_type in {"start_request", "submit_request"}:
            if session is None:
                receipts.append(
                    ActionReceipt(
                        action_id=f"req:{proposal.task_id}",
                        action_type=proposal.action_type,
                        state="failure",
                        reason="requests_db_unavailable",
                    )
                )
                continue
            receipts.append(
                persist_request(
                    session=session,
                    tenant_id=turn.tenant_id,
                    proposal=proposal,
                    channel=turn.channel,
                    customer_id=turn.customer_id,
                    conversation_id=turn.conversation_id,
                    message_id=inbound,
                    customer_text=customer_text,
                    current_revision=turn.state.draft_revision,
                )
            )
            continue
        receipts.append(
            ActionReceipt(
                action_id=f"{proposal.action_type}:{proposal.task_id}",
                action_type=proposal.action_type,
                state="rejected",
                reason="unsupported_action",
            )
        )
    return ActionReceiptSet(receipts=receipts)
