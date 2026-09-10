"""Customer Brain turn entry. Flag-off keeps the removed-engine contract."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.reply import TurnResult
from services.customer_ai.contracts.turn import CustomerTurn, MediaView
from services.customer_ai.control import apply_live_control
from services.customer_ai.flags import customer_brain_enabled
from services.customer_ai.gates import evaluate_gates
from services.customer_ai.comments.pipeline import deterministic_comment_result, winning_comment_mode
from services.customer_ai.history_store import load_history_snapshot
from services.customer_ai.turn_pipeline import run_dm_after_gates
from services.customer_reply_v2.models import ENGINE_REMOVED, CustomerReplyOutcome


def _outcome(result: TurnResult) -> CustomerReplyOutcome:
    reply = result.envelope.reply_text or None
    stop = result.stop_reason != "ok" or not reply
    return CustomerReplyOutcome(
        stop=stop,
        reply=reply,
        reason=result.stop_reason if result.stop_reason != "ok" else "",
        evidence_status="policy_stop" if stop else "ok",
        metadata={
            "ai_called": result.ai_called,
            "cost_status": "none" if not result.ai_called else "tracked",
            "customer_engine": "brain" if customer_brain_enabled() else "removed",
            **result.extra,
        },
    )


def _disabled(reason: str = ENGINE_REMOVED) -> TurnResult:
    return TurnResult(stop_reason="engine_removed" if reason == ENGINE_REMOVED else "brain_disabled")


async def _turn_from_dm(
    *,
    tenant_id: str,
    message: str,
    channel: str,
    conversation_id: str,
    user_id: str,
    inbound_media: dict[str, Any] | None,
    injected_history: list[dict[str, Any]] | None,
    message_id: str,
    followup_goal: str = "",
) -> CustomerTurn:
    media = inbound_media if isinstance(inbound_media, dict) else {}
    history = await load_history_snapshot(
        user_id=user_id,
        conversation_id=conversation_id,
        current_inbound_id="" if followup_goal else message_id,
        current_inbound_text="" if followup_goal else message,
        injected=injected_history,
    )
    return CustomerTurn(
        tenant_id=tenant_id,
        customer_id=user_id,
        conversation_id=conversation_id,
        channel=channel,
        surface="dm",
        invocation_kind="followup" if followup_goal else "dm",
        event_ids=[message_id] if message_id else [],
        history=history,
        followup_goal=followup_goal,
        media=MediaView(
            attachment_types=[str(t) for t in (media.get("attachment_types") or [])],
            transcript=str(media.get("transcript") or ""),
            extract_preview=str(media.get("extract") or media.get("file_extract_preview") or ""),
            inbound_link=str(media.get("inbound_link") or ""),
            image_media_id=str(media.get("image_media_id") or ""),
            safety_blocked=bool(media.get("safety_blocked")),
        ),
    )


async def run_customer_ai_dm(
    *,
    tenant_id: str,
    message: str,
    channel: str = "instagram_dm",
    conversation_id: str = "",
    user_id: str = "",
    inbound_media: dict[str, Any] | None = None,
    injected_history: list[dict[str, Any]] | None = None,
    message_id: str = "",
    apply_customer_usage_limits: bool = True,
    followup_goal: str = "",
    **_kwargs: Any,
) -> CustomerReplyOutcome:
    if not customer_brain_enabled():
        return _outcome(_disabled())
    turn = await _turn_from_dm(
        tenant_id=tenant_id,
        message=message,
        channel=channel,
        conversation_id=conversation_id,
        user_id=user_id,
        inbound_media=inbound_media,
        injected_history=injected_history,
        message_id=message_id,
        followup_goal=followup_goal or str(_kwargs.get("followup_goal") or ""),
    )
    turn = apply_live_control(turn)
    gate = evaluate_gates(turn, apply_credits=apply_customer_usage_limits, message=message)
    if not gate.allow:
        return _outcome(TurnResult(stop_reason=gate.reason, extra={"gate": gate.detail}))
    return _outcome(await run_dm_after_gates(turn, message=message, channel=channel))


async def run_customer_ai_comment(
    *,
    tenant_id: str,
    comment_text: str,
    channel: str = "instagram_comment",
    comments_enabled: bool = True,
    conversation_id: str = "",
    comment_id: str = "",
    post_id: str = "",
    **_kwargs: Any,
) -> CustomerReplyOutcome:
    if not comments_enabled:
        return CustomerReplyOutcome(stop=True, reason="comments_toggle_off", reply=None)
    if not customer_brain_enabled():
        return _outcome(_disabled())
    mode, decision = winning_comment_mode(
        tenant_id=tenant_id,
        comment_text=comment_text,
        post_id=post_id or str(_kwargs.get("post_id") or ""),
        channel=channel,
    )
    if mode and decision is not None:
        static = deterministic_comment_result(mode, decision, event_id=comment_id)
        if static is not None:
            return _outcome(static)
    from services.customer_ai.history import build_history_snapshot

    turn = CustomerTurn(
        tenant_id=tenant_id,
        conversation_id=conversation_id or f"comment:{tenant_id}:{channel}",
        channel=channel,
        surface="comment",
        invocation_kind="comment",
        event_ids=[comment_id] if comment_id else [],
        history=build_history_snapshot(
            None,
            current_inbound_id=comment_id,
            current_inbound_text=comment_text,
        ),
        extra={"comment_mode": mode or "", "winning_rule": getattr(decision, "rule_id", "")},
    )
    turn = apply_live_control(turn)
    gate = evaluate_gates(turn, message=comment_text)
    if not gate.allow:
        return _outcome(TurnResult(stop_reason=gate.reason, extra={"gate": gate.detail}))
    return _outcome(await run_dm_after_gates(turn, message=comment_text, channel=channel))
