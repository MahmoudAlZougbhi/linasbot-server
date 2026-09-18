"""Flag-on DM path after gates. Deterministic FAQ first; then agentic retrieve/generate."""

from __future__ import annotations

from services.brain.actions.pending import try_confirm_pending
from services.brain.contracts.reply import FinalReplyEnvelope, TurnResult
from services.brain.contracts.turn import CustomerTurn
from services.brain.faq_turn import exact_faq_result, semantic_faq_result
from services.brain.stage_timeline import stamp


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
    raw = (message or "").strip()
    if "post_caption=" in raw or "post_kind=" in raw:
        return raw
    parts: list[str] = []
    for item in (message, turn.media.transcript, turn.media.extract_preview):
        text = (item or "").strip()
        if text and text not in parts:
            parts.append(text)
    caption = str(turn.extra.get("post_caption") or "").strip()
    if caption and turn.surface == "comment":
        parts.append("post_caption=" + " ".join(caption.split()))
    media_type = str(turn.extra.get("post_media_type") or "").strip()
    if media_type and turn.surface == "comment":
        parts.append(f"post_kind={media_type}")
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
    """Do not prepend catalog/system greetings. Terra owns conversational copy."""
    _ = (turn, message, channel)
    return envelope


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
        from services.brain.silence import log_customer_generation_failure

        log_customer_generation_failure(stage="visual_disabled")
        return TurnResult(
            stop_reason="failed_closed",
            envelope=FinalReplyEnvelope(decision="clarify"),
            extra=_flow_extra(
                {"phase": "visual", "visual": visual.reason, "customer_silence": True, **flow_base},
                ("visual", "Image present but visual reading is disabled", {"reason": visual.reason}),
            ),
        )
    from services.brain.greeting_detect import is_greeting_only

    if is_greeting_only(message):
        from services.brain.agent.greeting_turn import identity_greeting_result

        greeted = await identity_greeting_result(turn, message=message, channel=channel, flow_base=flow_base)
        return greeted.model_copy(
            update={
                "extra": _flow_extra(
                    {**(greeted.extra or {}), **flow_base},
                    (
                        "greeting",
                        "Greeting-only turn used published Identity / Greeting Behavior / Style",
                        {"path": (greeted.extra or {}).get("path"), "retrieval_skipped": True},
                    ),
                )
            }
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
