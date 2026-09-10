"""Flag-on DM path after gates. Deterministic FAQ first; then retrieve/generate."""

from __future__ import annotations

from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.enums import SourceFamily, StopReason
from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.coverage import coverage_ok
from services.customer_ai.faq_exact import find_published_exact_faq
from services.customer_ai.generate.reply import generate_grounded_reply, openai_configured
from services.customer_ai.greeting import evaluate_greeting
from services.customer_ai.identity import load_identity_bundle
from services.customer_ai.planner.heuristic import plan_message
from services.customer_ai.retrieve.orchestrate import RetrieveContext, retrieve_published


def _destination(channel: str) -> str:
    return "web_chat" if "web" in (channel or "") else "dm"


def _faq_result(turn: CustomerTurn, message: str, channel: str) -> TurnResult | None:
    if turn.invocation_kind == "followup" or not message.strip():
        return None
    faq = find_published_exact_faq(turn.tenant_id, message)
    if not faq:
        return None
    destination = _destination(channel)
    messages: list[OutboundMessage] = []
    greet = evaluate_greeting(
        tenant_id=turn.tenant_id,
        message=message,
        history=turn.history,
        invocation_kind=turn.invocation_kind,
        already_greeted=turn.state.greeted,
    )
    if greet.eligible and greet.text:
        messages.append(OutboundMessage(destination=destination, text=greet.text, protected=True))
    messages.append(OutboundMessage(destination=destination, text=faq.answer, protected=True))
    return TurnResult(
        stop_reason="ok",
        envelope=FinalReplyEnvelope(
            decision="deterministic",
            messages=messages,
            used_evidence_ids=[f"faq:{faq.faq_id}"],
            dispositions={"faq": "answered"},
        ),
        extra={"path": "faq_exact", "faq_id": faq.faq_id, "faq_revision": faq.revision},
    )


def _families(plan_families: list[SourceFamily]) -> set[SourceFamily] | None:
    cleaned = {item for item in plan_families if item != "none"}
    return cleaned or None


def _stop_from_outcome(outcome: str) -> StopReason:
    if outcome in {"provider_not_configured", "index_not_ready", "unpublished", "context_overflow"}:
        return outcome  # type: ignore[return-value]
    if outcome == "source_unpublished":
        return "unpublished"
    return "failed_closed"


def _human_proposals(plan) -> ActionProposalSet:
    actions = [
        ActionProposal(task_id=task.id, action_type="escalate_to_human")
        for task in plan.tasks
        if task.type == "human_request"
    ]
    return ActionProposalSet(actions=actions)


async def run_dm_after_gates(turn: CustomerTurn, *, message: str, channel: str) -> TurnResult:
    faq = _faq_result(turn, message, channel)
    if faq:
        return faq
    task_text = message or turn.media.transcript or turn.followup_goal
    plan = plan_message(task_text)
    if any(task.type == "human_request" for task in plan.tasks):
        from services.customer_ai.actions.execute import execute_actions

        receipts = await execute_actions(turn=turn, proposals=_human_proposals(plan), customer_text=message)
        ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)
        return TurnResult(
            stop_reason="ok" if ok else "failed_closed",
            envelope=FinalReplyEnvelope(
                decision="handoff_ack" if ok else "no_reply",
                messages=[
                    OutboundMessage(destination=_destination(channel), text="A teammate will continue from here.")
                ]
                if ok
                else [],
                dispositions={"handoff": "action_succeeded" if ok else "failed"},
            ),
            extra={"phase": "handoff", "receipts": [r.model_dump() for r in receipts.receipts]},
        )
    if not plan.read_only:
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra={"phase": "actions_pending", "plan": plan.model_dump(), "awaiting_confirmation": True},
        )
    families: set[SourceFamily] = set()
    for task in plan.tasks:
        families |= _families(task.source_families) or set()
    bundle: EvidenceBundle = await retrieve_published(
        RetrieveContext(tenant_id=turn.tenant_id, query=task_text, families=families or None)
    )
    if bundle.outcome != "found":
        return TurnResult(
            stop_reason=_stop_from_outcome(bundle.outcome),
            envelope=FinalReplyEnvelope(decision="no_reply"),
            extra={"phase": "retrieve", "retrieval_outcome": bundle.outcome, "plan": plan.model_dump()},
        )
    if not openai_configured():
        return TurnResult(
            stop_reason="provider_not_configured",
            envelope=FinalReplyEnvelope(decision="no_reply", used_evidence_ids=[item.evidence_id for item in bundle.items]),
            extra={"phase": "awaiting_generate", "retrieval_outcome": bundle.outcome, "plan": plan.model_dump()},
        )
    identity = load_identity_bundle(turn.tenant_id)
    envelope = await generate_grounded_reply(
        turn=turn,
        message=task_text,
        plan=plan,
        bundle=bundle,
        identity=identity,
        destination=_destination(channel),
    )
    if envelope is None or not envelope.messages:
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra={"phase": "generate", "plan": plan.model_dump()},
        )
    if not coverage_ok(task_text, plan, envelope.dispositions):
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify", used_evidence_ids=envelope.used_evidence_ids),
            extra={"phase": "coverage", "plan": plan.model_dump()},
        )
    return TurnResult(stop_reason="ok", envelope=envelope, ai_called=True)
