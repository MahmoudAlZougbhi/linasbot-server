"""Stage and confirm request proposals across turns."""

from __future__ import annotations

from services.brain.actions.confirm import (
    material_fields_changed,
    next_draft_revision,
)
from services.brain.actions.request_fields import (
    collected_from_fields,
    merge_proposal_fields_with_prior,
    prior_collected_fields,
)
from services.brain.contracts.actions import ActionProposal, ActionProposalSet
from services.brain.contracts.reply import TurnResult
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
    dumped = [item.model_dump() for item in actions]
    remember_turn(turn, dumped)
    extra = dict(turn.extra or {})
    extra["pending_actions"] = dumped
    extra["awaiting_confirmation"] = True
    turn.extra = extra
    return ActionProposalSet(actions=actions)


async def try_confirm_pending(turn: CustomerTurn, message: str, channel: str) -> TurnResult | None:
    """Retired. Inbound wording never confirms a request or skips Terra."""
    _ = (turn, message, channel)
    return None


async def submit_pending_request(turn: CustomerTurn, args: dict) -> dict:
    """Persist because Terra called submit_request. Do not read the customer's words."""
    raw = load_conversation(turn.tenant_id, turn.conversation_id) or {}
    pending = [
        item for item in (raw.get("pending") or turn.extra.get("pending_actions") or []) if isinstance(item, dict)
    ]
    customer_text = str(args.get("customer_text") or args.get("text") or "")
    actions: list[ActionProposal] = []
    if pending:
        for item in pending:
            fields = merge_proposal_fields_with_prior(item.get("fields") or {}, pending)
            incoming = args.get("fields") if isinstance(args.get("fields"), dict) else {}
            if incoming:
                fields = merge_proposal_fields_with_prior({**fields, **incoming}, pending)
            fields = {**fields, "confirmation_text": customer_text}
            actions.append(ActionProposal.model_validate({**item, "action_type": "submit_request", "fields": fields}))
    else:
        fields = dict(args.get("fields") or {})
        for key in ("request_type", "title", "collected_fields", "draft_id", "request_id"):
            if key in args and key not in fields:
                fields[key] = args[key]
        if not str(fields.get("request_type") or "").strip():
            return {"ok": False, "error": "no_pending_draft", "data": None, "receipt": None}
        fields["confirmation_text"] = customer_text
        inbound = turn.event_ids[0] if turn.event_ids else ""
        actions.append(
            ActionProposal(
                task_id=str(args.get("task_id") or "terra"),
                action_type="submit_request",
                fields=fields,
                confirmation_message_id=inbound,
                expected_revision=str(turn.state.draft_revision or ""),
            )
        )
    receipts = await _execute(turn, ActionProposalSet(actions=actions), customer_text)
    ok = any(item.get("state") == "success" for item in receipts)
    if ok:
        remember_turn(turn, [])
        extra = dict(turn.extra or {})
        extra["pending_actions"] = []
        extra["awaiting_confirmation"] = False
        extra["request_receipts"] = receipts
        turn.extra = extra
    reason = None if ok else str((receipts[0] if receipts else {}).get("reason") or "submit_failed")
    return {
        "ok": ok,
        "data": {"receipts": receipts, "submitted": ok},
        "receipt": receipts[0] if receipts else None,
        "error": reason,
    }


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
