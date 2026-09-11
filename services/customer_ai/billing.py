"""Reserve/settle Customer AI message units around a finished turn."""

from __future__ import annotations

from services.customer_ai.contracts.reply import TurnResult
from services.customer_ai.contracts.turn import CustomerTurn
from services.membership.message_flags import message_billing_enabled
from services.membership.message_ledger import InsufficientMessages, reserve, settle
from services.membership.message_policy import ResponseClass, classify_turn, message_units_for
from services.membership.period_grants import ensure_included_grant


def operation_id_for_turn(turn: CustomerTurn) -> str:
    if turn.event_ids:
        return str(turn.event_ids[0])
    kind = turn.invocation_kind or "dm"
    return f"{turn.tenant_id}:{turn.conversation_id}:{kind}"


def owner_preview_turn(turn: CustomerTurn) -> bool:
    cid = (turn.conversation_id or "").strip().lower()
    op = operation_id_for_turn(turn)
    return cid.startswith("preview:") or op.startswith("sfu:preview:") or op.startswith("sfu-preview:")


_STATIC_COMMENT_MODES = frozenset({"ignore", "static_comment", "static_dm", "static_both", "manual"})
_AI_COMMENT_MODES = frozenset({"ai_comment", "ai_dm", "ai_both"})


def classify_result(turn: CustomerTurn, result: TurnResult) -> ResponseClass:
    extra = result.extra or {}
    path = str(extra.get("path") or "")
    phase = str(extra.get("phase") or "")
    mode = str(extra.get("comment_mode") or extra.get("rule_mode") or "")
    faq_used = bool(extra.get("faq_id") or extra.get("faq_used"))
    if path in {"faq_exact", "faq_semantic"} and not result.ai_called:
        return "faq_only"
    if mode in {"ignore", "manual"} or (
        path == "comment_rule" and (result.envelope.decision == "no_reply" or result.stop_reason == "policy_suppressed")
    ):
        return "no_reply"
    if path == "comment_rule" or mode in _STATIC_COMMENT_MODES:
        return "static"
    if phase == "followup_no_reply" or result.envelope.decision == "no_reply":
        return "no_reply"
    if result.stop_reason != "ok":
        return "operational_notice"
    if turn.invocation_kind == "followup" and result.envelope.messages:
        return "followup_sent"
    if faq_used and result.ai_called:
        return "mixed_faq_ai"
    if result.ai_called or mode in _AI_COMMENT_MODES:
        return "generated_ai"
    return classify_turn(generated=result.ai_called, faq_used=faq_used)


def accepted_for_delivery(result: TurnResult) -> bool:
    if result.stop_reason != "ok":
        return False
    return any(item.text.strip() for item in result.envelope.messages)


def _record_pending_llm(turn: CustomerTurn, operation_id: str) -> None:
    from services.membership.provider_expense import record_pending_provider

    record_pending_provider(
        event_id=f"llm:{operation_id}",
        tenant_id=turn.tenant_id,
        category="llm_generation",
        feature="customer_chat" if turn.invocation_kind != "followup" else "followup",
        provider="openai",
        model="answer",
        operation_id=operation_id,
    )


def _candidate_ids(turn: CustomerTurn, op: str) -> list[str]:
    seen: list[str] = []
    for item in (op, *turn.event_ids, turn.conversation_id):
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _pinned_policy(turn: CustomerTurn, op: str) -> str | None:
    from services.customer_ai.leftover_reserve import leftover_policy_for

    return leftover_policy_for(turn.tenant_id, op, *turn.event_ids, turn.conversation_id)


def _record_message_hold(turn: CustomerTurn, op: str) -> None:
    from services.membership.pending_settlement import record_hold

    record_hold(
        tenant_id=turn.tenant_id,
        reservation_id=op,
        operation_id=op,
        billing_policy="message_units",
        channel=turn.channel or turn.invocation_kind,
        extra={"candidate_ids": _candidate_ids(turn, op)},
    )


def _release_message_hold(tenant_id: str, op: str, *, reason: str) -> None:
    try:
        settle(tenant_id=tenant_id, operation_id=op, accepted=False)
    except KeyError:
        pass
    from services.membership.pending_settlement import get_pending, upsert

    if get_pending(tenant_id, op, op) is None:
        return
    upsert(
        tenant_id=tenant_id,
        reservation_id=op,
        operation_id=op,
        billing_policy="message_units",
        state="released",
        reason=reason,
    )


def apply_message_billing(turn: CustomerTurn, result: TurnResult) -> TurnResult:
    response_class = classify_result(turn, result)
    op = operation_id_for_turn(turn)
    extra = dict(result.extra)
    extra["response_class"] = response_class
    extra["message_units"] = message_units_for(response_class)
    extra["operation_id"] = op
    extra["legacy_comment_uncharged"] = turn.invocation_kind == "comment" and not message_billing_enabled()
    pinned = _pinned_policy(turn, op)
    extra["billing_policy"] = pinned or ("message_units" if message_billing_enabled() else "legacy_credits")
    if result.ai_called:
        _record_pending_llm(turn, op)
    if owner_preview_turn(turn):
        return result.model_copy(update={"extra": extra})
    if extra["billing_policy"] != "legacy_credits":
        ensure_included_grant(turn.tenant_id)
        accepted = accepted_for_delivery(result) and extra["message_units"] > 0
        try:
            try:
                if accepted:
                    reserve(tenant_id=turn.tenant_id, operation_id=op, response_class=response_class)
                    _record_message_hold(turn, op)
                    extra["billing_pending_send"] = True
                else:
                    _release_message_hold(turn.tenant_id, op, reason="not_accepted")
            except InsufficientMessages as exc:
                extra["billing"] = {"error": "insufficient_messages", "remaining": exc.remaining}
                return TurnResult(stop_reason="insufficient_messages", extra=extra)
        except Exception as exc:
            extra["billing"] = {"error": type(exc).__name__}
            if extra["message_units"]:
                return TurnResult(stop_reason="failed_closed", extra=extra)
    billed = result.model_copy(update={"extra": extra})
    from services.customer_ai.outbox import persist_turn_result

    persist_turn_result(turn, billed)
    return billed


def reserve_generative(turn: CustomerTurn, *, mixed: bool = False) -> TurnResult | None:
    op = operation_id_for_turn(turn)
    if not message_billing_enabled() or owner_preview_turn(turn) or _pinned_policy(turn, op) == "legacy_credits":
        return None
    ensure_included_grant(turn.tenant_id)
    if turn.invocation_kind == "followup":
        response_class: ResponseClass = "followup_sent"
    elif mixed:
        response_class = "mixed_faq_ai"
    else:
        response_class = "generated_ai"
    try:
        reserve(tenant_id=turn.tenant_id, operation_id=op, response_class=response_class)
        _record_message_hold(turn, op)
    except InsufficientMessages as exc:
        return TurnResult(
            stop_reason="insufficient_messages",
            extra={"billing": {"remaining": exc.remaining}, "response_class": response_class},
        )
    return None


def _candidate_ops(operation_id: str, extra_ids: tuple[str, ...] | list[str]) -> list[str]:
    seen: list[str] = []
    for item in (operation_id, *extra_ids):
        text = str(item or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def settle_after_send(
    *,
    tenant_id: str,
    operation_id: str,
    accepted: bool,
    channel: str = "",
    provider_message_id: str = "",
    response_class: ResponseClass = "generated_ai",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> None:
    candidates = _candidate_ops(operation_id, extra_ids)
    if not tenant_id or not candidates:
        return
    if not message_billing_enabled():
        if accepted:
            from services.customer_ai.outbox import acknowledge_sent

            acknowledge_sent(
                tenant_id=tenant_id,
                operation_id=candidates[0],
                provider_message_id=provider_message_id,
                extra_ids=candidates[1:],
            )
        else:
            from services.customer_ai.outbox import acknowledge_failed

            acknowledge_failed(tenant_id=tenant_id, operation_id=candidates[0], extra_ids=candidates[1:])
        return
    settled_op = ""
    try:
        for op in candidates:
            try:
                settle(tenant_id=tenant_id, operation_id=op, accepted=accepted)
                settled_op = op
                break
            except KeyError:
                continue
        if not settled_op:
            if not accepted:
                from services.customer_ai.outbox import acknowledge_failed

                acknowledge_failed(tenant_id=tenant_id, operation_id=candidates[0], extra_ids=candidates[1:])
                return
            from services.customer_ai.leftover_reserve import leftover_policy_for

            if leftover_policy_for(tenant_id, *candidates) == "legacy_credits":
                from services.customer_ai.outbox import acknowledge_sent

                acknowledge_sent(
                    tenant_id=tenant_id,
                    operation_id=candidates[0],
                    provider_message_id=provider_message_id,
                    extra_ids=candidates[1:],
                )
                return
            settled_op = candidates[0]
            reserve(tenant_id=tenant_id, operation_id=settled_op, response_class=response_class)
            settle(tenant_id=tenant_id, operation_id=settled_op, accepted=True)
        from services.membership.pending_settlement import upsert

        upsert(
            tenant_id=tenant_id,
            reservation_id=settled_op,
            operation_id=settled_op,
            billing_policy="message_units",
            state="settled" if accepted else "released",
            send_status="sent" if accepted else "",
            provider_message_id=provider_message_id,
            channel=channel,
            reason="send_settle",
            extra={"candidate_ids": candidates},
        )
        if accepted:
            from services.customer_ai.outbox import acknowledge_sent

            acknowledge_sent(
                tenant_id=tenant_id,
                operation_id=settled_op,
                provider_message_id=provider_message_id,
                extra_ids=candidates,
            )
        else:
            from services.customer_ai.outbox import acknowledge_failed

            acknowledge_failed(
                tenant_id=tenant_id,
                operation_id=settled_op,
                extra_ids=candidates,
            )
    except Exception:
        if accepted:
            from services.membership.reservation_reconcile import hold_failed_capture_after_send

            hold_failed_capture_after_send(
                tenant_id=tenant_id,
                reservation_id=settled_op or candidates[0],
                operation_id=settled_op or candidates[0],
                billing_policy="message_units",
                provider_message_id=provider_message_id,
                channel=channel or "customer_ai",
            )


def settle_followup_send(
    *,
    tenant_id: str,
    operation_id: str,
    accepted: bool,
    extra_ids: tuple[str, ...] | list[str] = (),
) -> None:
    settle_after_send(
        tenant_id=tenant_id,
        operation_id=operation_id,
        accepted=accepted,
        channel="smart_followup",
        response_class="followup_sent",
        extra_ids=extra_ids,
    )


def release_turn_reservation(turn: CustomerTurn) -> None:
    if not message_billing_enabled():
        return
    _release_message_hold(turn.tenant_id, operation_id_for_turn(turn), reason="generate_failed")
