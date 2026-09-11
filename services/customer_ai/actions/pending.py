"""Stage and confirm request proposals across turns."""

from __future__ import annotations

from services.customer_ai.actions.confirm import (
    looks_like_confirmation,
    material_fields_changed,
    next_draft_revision,
)
from services.customer_ai.actions.request_fields import (
    collected_from_fields,
    merge_proposal_fields_with_prior,
    prior_collected_fields,
)
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.conversation_store import load_conversation, remember_turn


def attach_confirmation(turn: CustomerTurn, proposals: ActionProposalSet) -> ActionProposalSet:
    inbound = turn.event_ids[0] if turn.event_ids else ""
    stored = load_conversation(turn.tenant_id, turn.conversation_id) or {}
    prior_pending = list(stored.get("pending") or turn.extra.get("pending_actions") or [])
    revision = turn.state.draft_revision or next_draft_revision("")
    actions = []
    confirmed: list[str] = []
    missing: list[str] = []
    for item in proposals.actions:
        fields = merge_proposal_fields_with_prior(item.fields, prior_pending)
        collected = collected_from_fields(fields)
        incoming_values = {
            key: value for key, value in collected_from_fields(item.fields).items() if str(value or "").strip()
        }
        prior_values = prior_collected_fields(prior_pending, str(fields.get("request_type") or ""))
        if incoming_values and material_fields_changed(prior_values, {**prior_values, **incoming_values}):
            revision = next_draft_revision(turn.state.draft_revision or revision)
        confirmed.extend(key for key, value in collected.items() if str(value or "").strip())
        missing.extend(key for key, value in collected.items() if not str(value or "").strip())
        actions.append(
            item.model_copy(
                update={
                    "fields": fields,
                    "expected_revision": item.expected_revision or revision,
                    "confirmation_message_id": item.confirmation_message_id or inbound,
                }
            )
        )
    turn.state = turn.state.model_copy(
        update={
            "draft_revision": revision,
            "confirmed_fields": list(dict.fromkeys(confirmed)),
            "missing_fields": list(dict.fromkeys(missing)),
        }
    )
    remember_turn(turn, [item.model_dump() for item in actions])
    return ActionProposalSet(actions=actions)


async def try_confirm_pending(turn: CustomerTurn, message: str, channel: str) -> TurnResult | None:
    if turn.invocation_kind in {"followup", "comment"}:
        return None
    if not (turn.channel or "").strip() and (channel or "").strip():
        turn.channel = channel
    raw = load_conversation(turn.tenant_id, turn.conversation_id)
    pending = list((raw or {}).get("pending") or turn.extra.get("pending_actions") or [])
    if not pending or not looks_like_confirmation(message):
        return None
    try:
        proposals = ActionProposalSet(
            actions=[
                ActionProposal.model_validate(
                    {
                        **item,
                        "fields": {
                            **merge_proposal_fields_with_prior(item.get("fields") or {}, pending),
                            "confirmation_text": message,
                        },
                    }
                )
                for item in pending
            ]
        )
    except Exception:
        return None
    receipts = await _execute(turn, proposals, message)
    ok = any(item.get("state") == "success" for item in receipts)
    if ok:
        remember_turn(turn, [])
    text = _confirm_reply(ok, receipts)
    destination = "web_chat" if "web" in (channel or turn.channel or "") else "dm"
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="deterministic" if ok else "clarify",
            messages=[OutboundMessage(destination=destination, text=text, protected=True)],
        ),
        extra={"phase": "request_confirm", "receipts": receipts, "confirmed": ok},
    )


async def _execute(turn: CustomerTurn, proposals: ActionProposalSet, message: str) -> list[dict]:
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.customer_ai.actions.execute import execute_actions

        try:
            with whatsapp_session(require=False) as session:
                receipts = await execute_actions(
                    turn=turn,
                    proposals=proposals,
                    customer_text=message,
                    session=session,
                )
        except WhatsAppDatabaseUnavailable:
            receipts = await execute_actions(turn=turn, proposals=proposals, customer_text=message)
        return [item.model_dump() for item in receipts.receipts]
    except Exception:
        return [{"action_type": "start_request", "state": "failure", "reason": "submit_failed"}]


def _confirm_reply(ok: bool, receipts: list[dict]) -> str:
    reasons = {str(item.get("reason") or "") for item in receipts}
    if ok:
        return "The request is submitted. A teammate will follow up if anything else is needed."
    if "REQUESTS_SETUP_REQUIRED" in reasons:
        return "This shop has not finished request setup yet, so I cannot submit that yet."
    if "confirmation_required" in reasons:
        return "I still need a clear yes to submit that request."
    if "invalid_source_channel" in reasons or "INVALID_SOURCE_CHANNEL" in reasons:
        return "I cannot submit that request from this channel yet."
    return "I could not submit that request yet. Please try again in a moment."
