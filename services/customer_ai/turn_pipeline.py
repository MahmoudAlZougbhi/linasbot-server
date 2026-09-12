"""Flag-on DM path after gates. Deterministic FAQ first; then agentic retrieve/generate."""

from __future__ import annotations

from services.customer_ai.actions.pending import try_confirm_pending
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.conversation_store import remember_turn
from services.customer_ai.faq_turn import exact_faq_result, semantic_faq_result
from services.customer_ai.greeting import evaluate_greeting
from services.customer_ai.stage_timeline import stamp
from services.customer_ai.templates import brain_template


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def _destination(channel: str, turn: object | None = None) -> str:
    from services.customer_ai.outbound_destination import outbound_destination

    return outbound_destination(turn, channel)


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
    destination = envelope.messages[0].destination or _destination(channel, turn)
    greeting = OutboundMessage(destination=destination, text=greet.text, protected=True)
    return envelope.model_copy(update={"messages": [greeting, *list(envelope.messages)]})


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
                        destination=_destination(channel, turn),
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

    from services.customer_ai.agent.loop import run_agentic_dm_path

    task_text = inbound_task_text(turn, message)
    return await run_agentic_dm_path(
        turn,
        message=task_text,
        channel=channel,
        flow_base={**flow_base, "visual": visual.reason},
        visual_reason=visual.reason,
    )
