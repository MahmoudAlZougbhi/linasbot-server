"""Flag-on DM path after gates. Deterministic FAQ first; then retrieve/generate."""

from __future__ import annotations

from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.enums import SourceFamily, StopReason
from services.customer_ai.contracts.evidence import EvidenceBundle
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.coverage import coverage_ok
from services.customer_ai.faq_turn import exact_faq_result, semantic_faq_result
from services.customer_ai.generate.reply import generate_grounded_reply, openai_configured
from services.customer_ai.greeting import evaluate_greeting
from services.customer_ai.identity import load_identity_bundle
from services.customer_ai.planner.openai_plan import plan_turn
from services.customer_ai.retrieve.orchestrate import RetrieveContext, retrieve_published
from services.customer_ai.actions.pending import attach_confirmation, try_confirm_pending
from services.customer_ai.billing import operation_id_for_turn, reserve_generative
from services.customer_ai.conversation_store import remember_turn
from services.customer_ai.stage_timeline import StageTimer, evidence_preview, stamp
from services.customer_ai.templates import brain_template


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def _destination(channel: str) -> str:
    return "web_chat" if "web" in (channel or "") else "dm"


def _response_language(turn: CustomerTurn) -> str:
    return str((turn.extra or {}).get("response_language") or "").strip()


def inbound_task_text(turn: CustomerTurn, message: str) -> str:
    parts: list[str] = []
    for item in (message, turn.media.transcript, turn.media.extract_preview):
        text = (item or "").strip()
        if text and text not in parts:
            parts.append(text)
    caption = str(turn.extra.get("post_caption") or "").strip()
    if caption and turn.surface == "comment":
        parts.insert(0, caption)
    return "\n".join(parts) or (turn.followup_goal or "")


def _apply_greeting(
    turn: CustomerTurn,
    message: str,
    channel: str,
    envelope: FinalReplyEnvelope,
) -> FinalReplyEnvelope:
    if turn.invocation_kind in {"followup", "comment"} or not envelope.messages:
        return envelope
    greet = evaluate_greeting(
        tenant_id=turn.tenant_id,
        message=message,
        history=turn.history,
        invocation_kind=turn.invocation_kind,
        already_greeted=turn.state.greeted,
    )
    if not (greet.eligible and greet.text):
        return envelope
    turn.state = turn.state.model_copy(update={"greeted": True})
    remember_turn(turn)
    destination = envelope.messages[0].destination or _destination(channel)
    greeting = OutboundMessage(destination=destination, text=greet.text, protected=True)
    return envelope.model_copy(update={"messages": [greeting, *list(envelope.messages)]})


def _families(plan_families: list[SourceFamily]) -> set[SourceFamily] | None:
    cleaned = {item for item in plan_families if item != "none"}
    return cleaned or None


def _stop_from_outcome(outcome: str) -> StopReason:
    if outcome in {
        "provider_not_configured",
        "index_not_ready",
        "product_index_stale",
        "unpublished",
        "context_overflow",
    }:
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


def _request_proposals(plan, *, tenant_id: str = "") -> ActionProposalSet:
    from services.customer_ai.actions.request_fields import published_request_fields

    actions = []
    for task in plan.tasks:
        if task.type == "service_request":
            kind = "APPOINTMENT"
        elif task.type == "product_request":
            kind = "ORDER"
        elif task.type == "cancel_or_status":
            actions.append(ActionProposal(task_id=task.id, action_type="cancel_request"))
            continue
        else:
            continue
        fields = {"request_type": kind, "title": task.span.text[:80], **published_request_fields(tenant_id, kind)}
        actions.append(ActionProposal(task_id=task.id, action_type="start_request", fields=fields))
    return ActionProposalSet(actions=actions)


def _history_blob(turn: CustomerTurn) -> str:
    return "\n".join(f"{item.role}: {item.text}" for item in turn.history.messages)


def _exact_faq_result(turn: CustomerTurn, message: str, channel: str) -> TurnResult | None:
    return exact_faq_result(turn, message, channel, apply_greeting=_apply_greeting)


async def _semantic_faq_result(turn: CustomerTurn, message: str, channel: str) -> TurnResult | None:
    return await semantic_faq_result(turn, message, channel, apply_greeting=_apply_greeting)


async def run_dm_after_gates(turn: CustomerTurn, *, message: str, channel: str) -> TurnResult:
    flow_base = _flow_extra(
        None,
        (
            "received",
            "Message received",
            {
                "channel": channel,
                "history_count": len(turn.history.messages),
                "inbound_preview": (message or turn.followup_goal or "")[:180],
            },
        ),
    )
    confirmed = await try_confirm_pending(turn, message, channel)
    if confirmed is not None:
        return confirmed.model_copy(
            update={
                "extra": _flow_extra(
                    {**(confirmed.extra or {}), **flow_base},
                    ("confirm", "Customer confirmed a pending request", {"phase": "confirm"}),
                )
            }
        )
    from services.customer_ai.visual import visual_retrieval_decision

    visual = visual_retrieval_decision(
        has_authorized_asset_id=bool(turn.media.inbound_link),
        requires_visual_reading=bool(turn.media.image_media_id),
    )
    if visual.reason == "disabled" and turn.media.image_media_id:
        lang = _response_language(turn)
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="clarify",
                messages=[
                    OutboundMessage(
                        destination=_destination(channel),
                        text=brain_template("visual_disabled", lang),
                    )
                ],
            ),
            extra=_flow_extra(
                {"phase": "visual", "visual": visual.reason, **flow_base},
                ("visual", "Image present but visual reading is disabled", {"reason": visual.reason}),
            ),
        )
    faq = _exact_faq_result(turn, message, channel) or await _semantic_faq_result(turn, message, channel)
    if faq:
        return faq.model_copy(
            update={
                "extra": _flow_extra(
                    {**(faq.extra or {}), **flow_base},
                    (
                        "faq",
                        "Answered from published FAQ",
                        {"faq_id": (faq.extra or {}).get("faq_id"), "path": (faq.extra or {}).get("path")},
                    ),
                )
            }
        )
    task_text = inbound_task_text(turn, message)
    from services.customer_ai.conversation_resolve import resolve_followup_query

    resolved = resolve_followup_query(task_text, turn.history.messages)
    if resolved.rewritten_query.strip() and resolved.rewritten_query.strip() != task_text.strip():
        task_text = resolved.rewritten_query
        flow_base = _flow_extra(
            flow_base,
            (
                "context",
                "Resolved follow-up using recent conversation",
                {"carry": resolved.carry, "used_turns": len(resolved.used_turns)},
            ),
        )
    plan_timer = StageTimer()
    plan = await plan_turn(
        task_text,
        _history_blob(turn),
        tenant_id=turn.tenant_id,
        operation_id=operation_id_for_turn(turn),
    )
    flow_base = _flow_extra(
        flow_base,
        (
            "plan",
            "Understood the customer request",
            {
                "ms": plan_timer.ms(),
                "plan_tasks": [{"id": task.id, "type": task.type} for task in plan.tasks],
            },
        ),
    )
    lang = _response_language(turn)
    if any(task.type == "human_request" for task in plan.tasks):
        from services.customer_ai.actions.execute import execute_actions

        receipts = await execute_actions(turn=turn, proposals=_human_proposals(plan), customer_text=message)
        ok = any(item.action_type == "escalate_to_human" and item.state == "success" for item in receipts.receipts)
        return TurnResult(
            stop_reason="ok" if ok else "failed_closed",
            envelope=FinalReplyEnvelope(
                decision="handoff_ack" if ok else "no_reply",
                messages=[
                    OutboundMessage(destination=_destination(channel), text=brain_template("handoff", lang))
                ]
                if ok
                else [],
                dispositions={"handoff": "action_succeeded" if ok else "failed"},
            ),
            extra=_flow_extra(
                {"phase": "handoff", "receipts": [r.model_dump() for r in receipts.receipts], **flow_base},
                ("handoff", "Handed off to a human teammate", {"decision": "handoff_ack" if ok else "no_reply"}),
            ),
        )
    request_proposals = _request_proposals(plan, tenant_id=turn.tenant_id)
    if request_proposals.actions:
        proposals = attach_confirmation(turn, request_proposals)
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="clarify",
                messages=[
                    OutboundMessage(
                        destination=_destination(channel),
                        text=brain_template("confirm_request", lang),
                    )
                ],
            ),
            extra=_flow_extra(
                {
                    "phase": "actions_pending",
                    "plan": plan.model_dump(),
                    "awaiting_confirmation": True,
                    "pending_actions": [item.model_dump() for item in proposals.actions],
                    **flow_base,
                },
                ("request", "Waiting for customer confirmation before submitting request", None),
            ),
        )
    families: set[SourceFamily] = set()
    for task in plan.tasks:
        families |= _families(task.source_families) or set()
    retrieve_timer = StageTimer()
    bundle: EvidenceBundle = await retrieve_published(
        RetrieveContext(tenant_id=turn.tenant_id, query=task_text, families=families or None)
    )
    evidence = evidence_preview(bundle)
    flow_base = _flow_extra(
        flow_base,
        (
            "search",
            "Searched published Knowledge / Services / Products / FAQ",
            {
                "ms": retrieve_timer.ms(),
                "retrieval_outcome": bundle.outcome,
                "evidence": evidence,
            },
        ),
    )
    resource_receipts: list[dict] = []
    resource_result = None
    if any(task.type == "resource_request" for task in plan.tasks):
        from services.customer_ai.actions.resource_turn import resource_request_result

        evidence_ids = [item.source_id for item in bundle.items] + [item.evidence_id for item in bundle.items]
        resource_result = await resource_request_result(
            turn,
            message=task_text,
            channel=channel,
            plan=plan,
            evidence_source_ids=evidence_ids,
        )
        info_tasks = [task for task in plan.tasks if task.type in {"information", "hours", "comparison"}]
        if resource_result is not None and not info_tasks:
            return resource_result.model_copy(
                update={
                    "extra": _flow_extra(
                        {**(resource_result.extra or {}), **flow_base, "evidence_preview": evidence},
                        ("resource", "Prepared authorized resource to send", None),
                    )
                }
            )
        if resource_result is not None:
            resource_receipts = list((resource_result.extra or {}).get("receipts") or [])
    if bundle.outcome != "found":
        if resource_result is not None:
            return resource_result.model_copy(
                update={"extra": {**(resource_result.extra or {}), **flow_base, "evidence_preview": evidence}}
            )
        return TurnResult(
            stop_reason=_stop_from_outcome(bundle.outcome),
            envelope=FinalReplyEnvelope(decision="no_reply"),
            extra=_flow_extra(
                {
                    "phase": "retrieve",
                    "retrieval_outcome": bundle.outcome,
                    "plan": plan.model_dump(),
                    "visual": visual.reason,
                    "receipts": resource_receipts,
                    "evidence_preview": evidence,
                    **flow_base,
                },
                ("search_empty", "No published evidence found for this question", {"retrieval_outcome": bundle.outcome}),
            ),
        )
    held = reserve_generative(turn, mixed=any(item.source_family == "faq" for item in bundle.items))
    if held is not None:
        return held
    result: TurnResult | None = None
    try:
        result = await _generate_after_reserve(
            turn,
            message=message,
            channel=channel,
            task_text=task_text,
            plan=plan,
            bundle=bundle,
            visual=visual,
            resource_receipts=resource_receipts,
        )
        merged = {**(result.extra or {}), **flow_base, "evidence_preview": evidence}
        if result.ai_called:
            merged = _flow_extra(
                merged,
                (
                    "generate",
                    "Composed grounded AI reply from evidence",
                    {
                        "decision": result.envelope.decision,
                        "used_evidence_ids": result.extra.get("used_evidence_ids") if result.extra else None,
                    },
                ),
            )
        result = result.model_copy(update={"extra": merged})
        return result
    except Exception:
        from services.customer_ai.billing import release_turn_reservation

        release_turn_reservation(turn)
        raise
    finally:
        if result is not None and not _keep_generate_hold(result):
            from services.customer_ai.billing import release_turn_reservation

            release_turn_reservation(turn)


def _keep_generate_hold(result: TurnResult) -> bool:
    return result.stop_reason == "ok" and any((item.text or "").strip() for item in result.envelope.messages)


async def _generate_after_reserve(
    turn: CustomerTurn,
    *,
    message: str,
    channel: str,
    task_text: str,
    plan,
    bundle: EvidenceBundle,
    visual,
    resource_receipts: list[dict] | None = None,
) -> TurnResult:
    if not openai_configured():
        return TurnResult(
            stop_reason="provider_not_configured",
            envelope=FinalReplyEnvelope(decision="no_reply", used_evidence_ids=[item.evidence_id for item in bundle.items]),
            extra={
                "phase": "awaiting_generate",
                "retrieval_outcome": bundle.outcome,
                "plan": plan.model_dump(),
                "receipts": list(resource_receipts or []),
            },
        )
    identity = load_identity_bundle(turn.tenant_id)
    envelope = await generate_grounded_reply(
        turn=turn,
        message=task_text,
        plan=plan,
        bundle=bundle,
        identity=identity,
        destination=_destination(channel),
        receipts=[
            f"{item.get('action_type')}:{item.get('state')}:{item.get('backend_id') or item.get('reason')}"
            for item in (resource_receipts or [])
        ],
    )
    if envelope is None or not envelope.messages:
        if turn.invocation_kind == "followup":
            return TurnResult(
                stop_reason="ok",
                envelope=FinalReplyEnvelope(decision="no_reply"),
                extra={"phase": "followup_no_reply", "plan": plan.model_dump(), "receipts": list(resource_receipts or [])},
            )
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra={"phase": "generate", "plan": plan.model_dump(), "receipts": list(resource_receipts or [])},
        )
    reply_text = "\n".join(item.text for item in envelope.messages if (item.text or "").strip())
    if not coverage_ok(
        task_text,
        plan,
        envelope.dispositions,
        reply_text=reply_text,
        decision=envelope.decision,
    ):
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify", used_evidence_ids=envelope.used_evidence_ids),
            extra={"phase": "coverage", "plan": plan.model_dump(), "receipts": list(resource_receipts or [])},
        )
    faq_items = [item for item in bundle.items if item.source_family == "faq"]
    dispositions = dict(envelope.dispositions)
    for task in plan.tasks:
        if task.type == "resource_request" and task.id not in dispositions:
            dispositions[task.id] = "pending_delivery" if resource_receipts else "not_found"
    extra = {
        "phase": "generate",
        "plan": plan.model_dump(),
        "visual": visual.reason,
        "faq_used": bool(faq_items),
        "faq_id": faq_items[0].source_id if faq_items else "",
        "used_evidence_ids": list(envelope.used_evidence_ids),
        "receipts": list(resource_receipts or []),
    }
    return TurnResult(
        stop_reason="ok",
        envelope=_apply_greeting(turn, message, channel, envelope.model_copy(update={"dispositions": dispositions})),
        ai_called=True,
        extra=extra,
    )
