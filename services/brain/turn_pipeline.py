"""Flag-on DM path after gates. Deterministic FAQ first; then agentic retrieve/generate."""

from __future__ import annotations

from services.brain.actions.pending import try_confirm_pending
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_store import remember_turn
from services.brain.faq_turn import exact_faq_result, semantic_faq_result
from services.brain.greeting import evaluate_greeting, inbound_greeting_language, is_greeting_only, safe_greeting_text
from services.brain.stage_timeline import stamp
from services.brain.templates import brain_template


def _flow_extra(extra: dict | None, *rows: tuple[str, str, dict | None]) -> dict:
    out = dict(extra or {})
    for stage, title, detail in rows:
        out = stamp(out, stage, title=title, detail=detail)
    return out


def _destination(channel: str, turn: object | None = None) -> str:
    from services.brain.outbound_destination import outbound_destination

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
    media_type = str(turn.extra.get("post_media_type") or "").strip()
    if media_type and turn.surface == "comment":
        parts.append(f"post_media_type={media_type}")
    visual = str(turn.extra.get("post_visual_description") or "").strip()
    if visual:
        parts.append(f"post_visual={visual}")
    post_transcript = str(turn.extra.get("post_transcript") or "").strip()
    if post_transcript and post_transcript not in parts:
        parts.append(f"post_audio_transcript={post_transcript}")
    urls = [str(item).strip() for item in (turn.extra.get("post_image_urls") or []) if str(item).strip()]
    if urls and turn.surface == "comment" and not visual:
        parts.append(f"post_media_url={urls[0]}")
    return "\n".join(parts) or (turn.followup_goal or "")


def _apply_greeting(
    turn: CustomerTurn,
    message: str,
    channel: str,
    envelope: FinalReplyEnvelope,
) -> FinalReplyEnvelope:
    if turn.invocation_kind in {"followup", "comment"} or not envelope.messages:
        return envelope
    if is_greeting_only(message):
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
    from services.brain.outbound_safety import is_customer_safe_opener

    if not is_customer_safe_opener(greet.text):
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
        {
            "tenant_id": turn.tenant_id,
            "response_language": _response_language(turn),
        },
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
    from services.brain.visual import visual_retrieval_decision

    visual = visual_retrieval_decision(
        has_authorized_asset_id=bool(turn.media.inbound_link),
        requires_visual_reading=bool(turn.media.image_media_id),
    )
    analyzed = bool(
        (turn.media.extract_preview or "").strip()
        or (turn.media.transcript or "").strip()
        or str((turn.extra or {}).get("post_visual_description") or "").strip()
        or str((turn.extra or {}).get("post_transcript") or "").strip()
    )
    if visual.reason == "disabled" and turn.media.image_media_id and not analyzed:
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
    from services.brain.agent.greeting_turn import identity_greeting_result

    try:
        greeted = await identity_greeting_result(turn, message=message, channel=channel, flow_base=flow_base)
    except Exception as exc:
        print(f"[run_dm_after_gates] identity_greeting fail-soft {type(exc).__name__}: {str(exc)[:200]}")
        greeted = None
    if greeted is not None:
        return greeted
    if is_greeting_only(message):
        lang = _response_language(turn) or inbound_greeting_language(message)
        text = safe_greeting_text(
            tenant_id=turn.tenant_id,
            message=message,
            language=lang,
            history=turn.history,
        )
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination=_destination(channel, turn), text=text)],
            ),
            extra=_flow_extra(
                {"phase": "identity_greeting", "path": "identity_greeting_fail_soft", **flow_base},
                ("greeting", "Greeting-only fail-soft catalog opener", {"ai_called": False}),
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

    from services.brain.agent.loop import run_agentic_dm_path

    task_text = inbound_task_text(turn, message)
    return await run_agentic_dm_path(
        turn,
        message=task_text,
        channel=channel,
        flow_base={**flow_base, "visual": visual.reason},
        visual_reason=visual.reason,
    )
