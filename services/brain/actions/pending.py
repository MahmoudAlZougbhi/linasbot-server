"""Stage and confirm request proposals across turns."""

from __future__ import annotations

from services.brain.actions.confirm import (
    looks_like_confirmation,
    material_fields_changed,
    next_draft_revision,
)
from services.brain.actions.request_fields import (
    collected_from_fields,
    merge_proposal_fields_with_prior,
    prior_collected_fields,
)
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_store import load_conversation, remember_turn


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
    if not ok:
        from services.brain.silence import log_customer_generation_failure

        log_customer_generation_failure(
            stage="request_persist_failed",
            extra={"receipts": receipts, "tenant_id": turn.tenant_id},
        )
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="no_reply", messages=[]),
            extra={"phase": "request_confirm", "receipts": receipts, "confirmed": False, "customer_silence": True},
        )
    remember_turn(turn, [])
    from services.brain.templates import owner_protocol_text
    from services.brain.outbound_destination import outbound_destination

    lang = str((turn.extra or {}).get("response_language") or "")
    text = owner_protocol_text("confirm_request", lang)
    destination = outbound_destination(turn, channel)
    messages = []
    if text:
        messages = [OutboundMessage(destination=destination, text=text, protected=True)]
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(decision="deterministic", messages=messages),
        extra={"phase": "request_confirm", "receipts": receipts, "confirmed": True},
    )


async def _execute(turn: CustomerTurn, proposals: ActionProposalSet, message: str) -> list[dict]:
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.brain.actions.execute import execute_actions

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
