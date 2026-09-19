"""Customer Brain turn entry. Brain is the permanent customer reply runtime."""

from __future__ import annotations

from typing import Any, Literal

from services.brain.billing import apply_message_billing, operation_id_for_turn
from services.brain.channel_plan import assert_channel_plan_allowed, denied_code
from services.brain.comments.pipeline import deterministic_comment_result, winning_comment_mode
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import CustomerTurn, MediaView
from services.brain.control import apply_live_control
from services.brain.conversation_history import record_turn_history
from services.brain.conversation_store import hydrate_turn_state, remember_turn
from services.brain.gates import GateDecision, evaluate_gates
from services.brain.history_ids import bind_dm_ids, comment_conversation_id
from services.brain.history_store import load_history_snapshot
from services.brain.reply.models import CustomerReplyOutcome
from services.brain.turn_pipeline import run_dm_after_gates


def _scrub_instruction_reply(result: TurnResult, reply: str | None) -> tuple[str | None, dict[str, Any]]:
    extra = dict(result.extra or {})
    text = (reply or "").strip()
    if not text:
        return reply, extra
    from services.brain.outbound_safety import looks_like_instruction_text

    if not looks_like_instruction_text(text):
        return reply, extra
    tenant_id = str(extra.get("tenant_id") or "")
    lang = str(extra.get("response_language") or "")
    inbound = str(extra.get("inbound_preview") or "")
    path = str(extra.get("path") or extra.get("phase") or "")
    extra["outbound_instruction_blocked"] = True
    extra["blocker"] = str(extra.get("blocker") or "outbound_instruction_blocked")[:200]
    extra["exception_class"] = str(extra.get("exception_class") or "OutboundInstructionBlocked")
    extra["outbound_replacement"] = "silence"
    extra["customer_silence"] = True
    _ = (tenant_id, lang, inbound, path)
    from services.brain.silence import log_customer_generation_failure

    log_customer_generation_failure(stage="outbound_instruction_blocked", extra=extra)
    return None, extra


def _outcome(result: TurnResult, *, comment_surface: bool = False) -> CustomerReplyOutcome:
    extra = dict(result.extra or {})
    safe_messages = []
    for item in result.envelope.messages:
        text, extra = _scrub_instruction_reply(result, item.text)
        if text:
            safe_messages.append(item.model_copy(update={"text": text}))
    public_raw = result.envelope.public_comment_text
    private_raw = result.envelope.private_dm_text
    public, extra = _scrub_instruction_reply(result, public_raw or None)
    private, extra = _scrub_instruction_reply(result, private_raw or None)
    if comment_surface:
        reply = public or None
        has_out = bool(public or private)
    else:
        reply = (safe_messages[0].text if safe_messages else None) or (result.envelope.reply_text or None)
        reply, extra = _scrub_instruction_reply(result, reply)
        has_out = bool(reply)
    stop = result.stop_reason != "ok" or not has_out
    return CustomerReplyOutcome(
        stop=stop,
        reply=reply,
        reason=result.stop_reason if result.stop_reason != "ok" else "",
        evidence_status="policy_stop" if stop else "ok",
        metadata={
            "ai_called": result.ai_called,
            "cost_status": "none" if not result.ai_called else "tracked",
            "customer_engine": "brain",
            "outbound_messages": [item.model_dump() for item in safe_messages],
            "public_comment_text": public or "",
            "private_dm_text": private or "",
            **extra,
            "operation_id": extra.get("operation_id") or "",
        },
    )


def _destination_for(turn: CustomerTurn, channel: str) -> str:
    from services.brain.outbound_destination import outbound_destination

    return outbound_destination(turn, channel or turn.channel)


def _gate_result(turn: CustomerTurn, gate: GateDecision, channel: str) -> TurnResult:
    extra = {"gate": gate.detail}
    if gate.reason == "restricted" and gate.reply_text:
        extra["restricted_topic_id"] = gate.detail
        return TurnResult(
            stop_reason="restricted",
            envelope=FinalReplyEnvelope(
                decision="deterministic",
                messages=[
                    OutboundMessage(destination=_destination_for(turn, channel), text=gate.reply_text, protected=True)
                ],
            ),
            extra=extra,
        )
    return TurnResult(stop_reason=gate.reason, extra=extra)


async def _run_billed(turn: CustomerTurn, *, message: str, channel: str) -> TurnResult:
    from services.brain.billing import release_turn_reservation

    try:
        return apply_message_billing(turn, await run_dm_after_gates(turn, message=message, channel=channel))
    except Exception:
        release_turn_reservation(turn)
        raise


def _language_extra(*, detected_language: str = "", response_language: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    detected = (detected_language or "").strip()
    response = (response_language or "").strip()
    if detected:
        out["detected_language"] = detected
    if response:
        out["response_language"] = response
    return out


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
    detected_language: str = "",
    response_language: str = "",
) -> CustomerTurn:
    media = inbound_media if isinstance(inbound_media, dict) else {}
    conversation_id, message_id = bind_dm_ids(
        conversation_id=conversation_id,
        user_id=user_id,
        message_id=message_id,
        message=message,
        followup_goal=followup_goal,
        payload=media,
    )
    history = await load_history_snapshot(
        user_id=user_id,
        conversation_id=conversation_id,
        current_inbound_id="" if followup_goal else message_id,
        current_inbound_text="" if followup_goal else message,
        injected=injected_history,
        tenant_id=tenant_id,
        channel=channel,
    )
    extra = _language_extra(detected_language=detected_language, response_language=response_language)
    matches = media.get("product_image_matches")
    if isinstance(matches, list) and matches:
        extra["product_image_matches"] = matches
    return hydrate_turn_state(
        CustomerTurn(
            tenant_id=tenant_id,
            customer_id=user_id,
            conversation_id=conversation_id,
            channel=channel,
            surface="dm",
            invocation_kind="followup" if followup_goal else "dm",
            event_ids=[message_id] if message_id else [],
            history=history,
            followup_goal=followup_goal,
            extra=extra,
            media=MediaView(
                attachment_types=[str(t) for t in (media.get("attachment_types") or [])],
                transcript=str(media.get("transcript") or ""),
                extract_preview=str(media.get("extract") or media.get("file_extract_preview") or ""),
                inbound_link=str(media.get("inbound_link") or ""),
                image_media_id=str(media.get("image_media_id") or ""),
                safety_blocked=bool(media.get("safety_blocked")),
            ),
        )
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
    from services.brain.tenant_gate import evaluate_brain_tenant_gate

    gate_tenant = evaluate_brain_tenant_gate(tenant_id)
    if not gate_tenant.get("allow"):
        return CustomerReplyOutcome(
            stop=True,
            reply=None,
            reason=str(gate_tenant.get("reason") or "missing_tenant"),
            evidence_status="policy_stop",
            metadata={
                "ai_called": False,
                "cost_status": "none",
                "customer_engine": "brain",
                "tenant_gate": gate_tenant,
            },
        )
    try:
        assert_channel_plan_allowed(tenant_id, channel)
        if followup_goal or _kwargs.get("followup_goal"):
            from services.billing.membership.feature_entitlements import FeatureDenied, assert_followup_allowed

            assert_followup_allowed(tenant_id)
    except Exception as exc:
        from services.billing.membership.feature_entitlements import FeatureDenied

        if isinstance(exc, FeatureDenied):
            return CustomerReplyOutcome(stop=True, reason=exc.code, reply=None)
        reason = denied_code(exc)
        if reason:
            return CustomerReplyOutcome(stop=True, reason=reason, reply=None)
        raise
    turn = await _turn_from_dm(
        tenant_id=tenant_id,
        message=message,
        channel=channel,
        conversation_id=conversation_id,
        user_id=user_id or str(_kwargs.get("provider_sender_id") or ""),
        inbound_media=inbound_media,
        injected_history=injected_history,
        message_id=message_id,
        followup_goal=followup_goal or str(_kwargs.get("followup_goal") or ""),
        detected_language=str(_kwargs.get("detected_language") or ""),
        response_language=str(_kwargs.get("response_language") or ""),
    )
    turn = apply_live_control(turn)
    remember_turn(turn)
    gate = evaluate_gates(turn, apply_credits=apply_customer_usage_limits, message=message)
    if not gate.allow:
        gated = _gate_result(turn, gate, channel)
        record_turn_history(turn, inbound_id=message_id, inbound_text=message, result=gated)
        return _outcome(gated)
    if not (turn.conversation_id or "").strip() or (not turn.event_ids and not (turn.followup_goal or followup_goal)):
        closed = TurnResult(stop_reason="failed_closed", extra={"reason": "inbound_ids_required"})
        record_turn_history(turn, inbound_id=message_id, inbound_text=message, result=closed)
        return _outcome(closed)
    result = await _run_billed(turn, message=message, channel=channel)
    record_turn_history(turn, inbound_id=message_id, inbound_text=message, result=result)
    remember_turn(turn)
    extra = dict(result.extra)
    extra.setdefault("operation_id", operation_id_for_turn(turn))
    return _outcome(result.model_copy(update={"extra": extra}))


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
    from services.brain.tenant_gate import evaluate_brain_tenant_gate

    gate_tenant = evaluate_brain_tenant_gate(tenant_id)
    if not gate_tenant.get("allow"):
        return CustomerReplyOutcome(
            stop=True,
            reply=None,
            reason=str(gate_tenant.get("reason") or "missing_tenant"),
            evidence_status="policy_stop",
            metadata={
                "ai_called": False,
                "cost_status": "none",
                "customer_engine": "brain",
                "tenant_gate": gate_tenant,
            },
        )
    try:
        from services.billing.membership.comment_gate import assert_comment_automation_allowed

        assert_comment_automation_allowed(tenant_id)
        assert_channel_plan_allowed(tenant_id, channel)
    except Exception as exc:
        reason = denied_code(exc)
        if reason:
            return CustomerReplyOutcome(stop=True, reason=reason, reply=None)
        raise
    sender = str(_kwargs.get("provider_sender_id") or "").strip()
    post_id_value = post_id or str(_kwargs.get("post_id") or "")
    conv_id = comment_conversation_id(
        tenant_id=tenant_id,
        conversation_id=conversation_id,
        channel=channel,
        post_id=post_id_value,
        author_id=sender,
    )
    stub = apply_live_control(
        CustomerTurn(
            tenant_id=tenant_id,
            conversation_id=conv_id,
            channel=channel,
            surface="comment",
            invocation_kind="comment",
            event_ids=[comment_id] if comment_id else [],
        )
    )
    gate = evaluate_gates(stub, apply_credits=False, message=comment_text)
    if not gate.allow:
        gated = _gate_result(stub, gate, channel)
        record_turn_history(
            stub,
            inbound_id=comment_id,
            inbound_text=comment_text,
            result=gated,
            comment_surface=True,
        )
        return _outcome(gated, comment_surface=True)
    mode, decision = winning_comment_mode(
        tenant_id=tenant_id,
        comment_text=comment_text,
        post_id=post_id_value,
        channel=channel,
    )
    if mode and decision is not None:
        static = deterministic_comment_result(mode, decision, event_id=comment_id)
        if static is not None:
            static_turn = CustomerTurn(
                tenant_id=tenant_id,
                conversation_id=conv_id,
                channel=channel,
                surface="comment",
                invocation_kind="comment",
                event_ids=[comment_id] if comment_id else [],
            )
            billed = apply_message_billing(static_turn, static)
            record_turn_history(
                static_turn,
                inbound_id=comment_id,
                inbound_text=comment_text,
                result=billed,
                comment_surface=True,
            )
            return _outcome(billed, comment_surface=True)
    from services.billing.membership.generative_gate import generative_block_reason

    blocked = generative_block_reason(tenant_id)
    if blocked:
        stop_reason: Literal["unpublished", "insufficient_messages"] = (
            "unpublished" if blocked == "unpublished" else "insufficient_messages"
        )
        gated = TurnResult(stop_reason=stop_reason, extra={"gate": blocked})
        record_turn_history(
            stub,
            inbound_id=comment_id,
            inbound_text=comment_text,
            result=gated,
            comment_surface=True,
        )
        return _outcome(gated, comment_surface=True)
    from services.brain.history import build_history_snapshot

    parent = str(_kwargs.get("parent_comment") or "").strip()
    caption = str(_kwargs.get("caption") or "").strip()
    raw_ctx = _kwargs.get("comment_context")
    ctx: dict[str, Any] = raw_ctx if isinstance(raw_ctx, dict) else {}
    media_type = str(_kwargs.get("media_type") or ctx.get("media_type") or "").strip()
    image_urls = [
        str(item).strip() for item in (_kwargs.get("image_urls") or ctx.get("image_urls") or []) if str(item).strip()
    ]
    video_url = str(_kwargs.get("video_url") or ctx.get("video_url") or "").strip()
    from services.brain.media.comment_attach import analysis_fields_for_comment

    media_fields = await analysis_fields_for_comment(
        tenant_id=tenant_id,
        post_id=post_id_value,
        media_type=media_type,
        urls=image_urls,
        video_url=video_url,
        caption=caption,
        context=ctx,
    )
    history = await load_history_snapshot(
        user_id=sender or f"comment:{comment_id or conv_id}",
        conversation_id=conv_id,
        current_inbound_id=comment_id,
        current_inbound_text=comment_text,
        tenant_id=tenant_id,
        channel=channel,
    )
    if parent:
        prior = [{"id": f"parent:{comment_id or 'c'}", "role": "user", "text": parent}]
        history = build_history_snapshot(
            prior + [item.model_dump() for item in history.messages],
            current_inbound_id=comment_id,
            current_inbound_text=comment_text,
        )
    turn = hydrate_turn_state(
        CustomerTurn(
            tenant_id=tenant_id,
            customer_id=sender,
            conversation_id=conv_id,
            channel=channel,
            surface="comment",
            invocation_kind="comment",
            event_ids=[comment_id] if comment_id else [],
            history=history,
            extra={
                "comment_mode": mode or "",
                "comment_channel": channel,
                "winning_rule": getattr(decision, "rule_id", ""),
                "comment_rule_text": str(getattr(decision, "policy_text", "") or ""),
                "post_caption": caption,
                "post_id": post_id_value,
                "post_media_type": media_type,
                "post_image_urls": image_urls,
                **media_fields,
                **_language_extra(
                    detected_language=str(_kwargs.get("detected_language") or ""),
                    response_language=str(_kwargs.get("response_language") or ""),
                ),
            },
        )
    )
    turn = apply_live_control(turn)
    remember_turn(turn)
    from services.brain.billing import release_turn_reservation
    from services.brain.comments.pipeline import apply_ai_comment_destinations

    try:
        generated = await run_dm_after_gates(turn, message=comment_text, channel=channel)
        generated = apply_ai_comment_destinations(generated, mode, channel=channel)
        billed = apply_message_billing(turn, generated)
    except Exception:
        release_turn_reservation(turn)
        raise
    record_turn_history(
        turn,
        inbound_id=comment_id,
        inbound_text=comment_text,
        result=billed,
        comment_surface=True,
    )
    remember_turn(turn)
    extra = dict(billed.extra)
    extra.setdefault("operation_id", operation_id_for_turn(turn))
    extra["comment_mode"] = mode or ""
    return _outcome(billed.model_copy(update={"extra": extra}), comment_surface=True)
