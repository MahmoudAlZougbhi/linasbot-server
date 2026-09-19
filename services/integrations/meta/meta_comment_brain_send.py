"""Brain comment generation and destination send. One Comments decision path."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from services.brain.comments.destinations import CommentDestinations

if TYPE_CHECKING:
    from services.integrations.meta.meta_comment_replies import CommentReplyResult
from services.integrations.meta.meta_comment_rule_both import (
    _dm_payload,
    _guarded_private_dm,
    _guarded_public_reply,
    _public_payload,
)

_runtime_logger = logging.getLogger("uvicorn.error")


class MetaCommentReplyGenerationError(RuntimeError):
    """Transient AI generation failure that should remain eligible for retry."""


async def generate_comment_reply_text(
    *,
    tenant_id: str,
    comment_text: str,
    instructions: str,
    channel: str,
    policy_text: str = "",
    comment_context: dict[str, Any] | None = None,
    asset_id: str = "",
    provider_sender_id: str = "",
    provider_display_name: str = "",
) -> Any:
    """Generate comment destinations via Customer Brain only (static, FAQ, or Terra)."""
    from services.ai_setup.language_policy import detect_and_resolve_customer_languages
    from services.brain.history_ids import comment_conversation_id
    from services.brain.reply.comment_runtime import run_customer_reply_v2_comment

    ctx = dict(comment_context or {})
    thread_id = comment_conversation_id(
        tenant_id=tenant_id,
        channel=channel,
        post_id=str(ctx.get("post_id") or ""),
        author_id=provider_sender_id,
    )
    languages = detect_and_resolve_customer_languages(
        tenant_id=tenant_id,
        message=comment_text,
        conversation_id=thread_id,
    )
    social_channel = "facebook_comment" if channel == "facebook" else "instagram_comment"
    ctx.pop("conversation_id", None)
    if instructions and "asset_instructions" not in ctx:
        ctx["asset_instructions"] = instructions.strip()[:800]
    if policy_text and "comments_policy" not in ctx:
        ctx["comments_policy"] = {"policy_text": policy_text.strip()[:1200]}
    try:
        outcome = await run_customer_reply_v2_comment(
            tenant_id=tenant_id,
            comment_text=comment_text,
            detected_language=languages["detected_language"],
            response_language=languages["response_language"],
            channel=social_channel,
            asset_id=asset_id,
            provider_sender_id=provider_sender_id,
            provider_display_name=provider_display_name,
            comments_enabled=True,
            comment_id=str(ctx.get("comment_id") or ""),
            post_id=str(ctx.get("post_id") or ""),
            caption=str(ctx.get("caption") or ""),
            parent_comment=str(ctx.get("parent_comment") or ""),
            media_type=str(ctx.get("media_type") or ""),
            image_urls=list(ctx.get("image_urls") or []) or None,
            comment_context=ctx or None,
        )
    except Exception as exc:
        _runtime_logger.warning("customer_reply_v2 comment path failed closed: %s", type(exc).__name__)
        raise MetaCommentReplyGenerationError("customer reply generation failed") from exc
    from services.brain.comments.destinations import destinations_from_outcome

    plan = destinations_from_outcome(outcome)
    return plan if plan.has_any else None


async def send_comment_destinations(
    *,
    plan: CommentDestinations,
    binding: Any,
    comment_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
    inbound_event_id: str | None,
    token: str,
    graph_api_version: str,
    client: Any,
    skip_public: bool = False,
    rule_decision: Any = None,
) -> CommentReplyResult:
    from services.integrations.meta.meta_comment_replies import CommentReplyResult, _mark_sent_reply

    public = "" if skip_public else plan.public_text
    private = plan.private_text
    if plan.public_depends_on_private and not private:
        public = ""
    billable = str(plan.comment_mode or "").startswith("ai")
    if not public and not private:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id="",
            accepted=False,
            billable=False,
        )
        return CommentReplyResult(status="skipped", reason="no_confident_reply")
    rule_id = plan.comment_mode or "brain"

    if simulation:
        if capture_send is not None:
            if private:
                capture_send.append(_dm_payload(comment_id=comment_id, binding=binding, text=private, rule_id=rule_id))
            if public:
                capture_send.append(
                    _public_payload(comment_id=comment_id, binding=binding, text=public, rule_id=rule_id)
                )
        _mark_sent_reply(binding, comment_id)
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id="simulated",
            accepted=False,
            billable=False,
        )
        await _maybe_send_resources(
            rule_decision=rule_decision,
            binding=binding,
            comment_id=comment_id,
            simulation=True,
            capture_send=capture_send,
        )
        if public and private:
            return CommentReplyResult(status="simulated_both", reply_id="simulated_both")
        if private and not public:
            return CommentReplyResult(status="simulated", reply_id="simulated")
        return CommentReplyResult(status="simulated", reply_id="simulated")

    if client is None:
        _settle_comment_send(
            binding=binding,
            comment_id=comment_id,
            inbound_event_id=inbound_event_id,
            reply_id="",
            accepted=False,
            billable=billable,
        )
        return CommentReplyResult(status="failed", reason="comment_send_client_missing")

    dm_result: dict[str, Any] = {"skipped": True}
    public_result: dict[str, Any] = {"skipped": True}
    if private:
        dm_result = await _guarded_private_dm(
            client=client,
            binding=binding,
            comment_id=comment_id,
            message=private,
            token=token,
            graph_api_version=graph_api_version,
            inbound_event_id=inbound_event_id,
        )
        if plan.public_depends_on_private and not dm_result.get("ok"):
            public = ""
        if dm_result.get("hard_fail") and not public:
            _settle_comment_send(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                reply_id="",
                accepted=False,
                billable=billable,
            )
            return CommentReplyResult(
                status=str(dm_result.get("status") or "failed"),
                reason=str(dm_result.get("reason") or "private_reply_failed"),
            )
    if public:
        public_result = await _guarded_public_reply(
            client=client,
            binding=binding,
            comment_id=comment_id,
            message=public,
            token=token,
            graph_api_version=graph_api_version,
            inbound_event_id=inbound_event_id,
        )
        if public_result.get("hard_fail") and not dm_result.get("ok"):
            _settle_comment_send(
                binding=binding,
                comment_id=comment_id,
                inbound_event_id=inbound_event_id,
                reply_id="",
                accepted=False,
                billable=billable,
            )
            return CommentReplyResult(
                status=str(public_result.get("status") or "failed"),
                reason=str(public_result.get("reason") or "public_reply_failed"),
            )

    _mark_sent_reply(binding, comment_id)
    public_ok = bool(public_result.get("ok") or public_result.get("duplicate"))
    dm_ok = bool(dm_result.get("ok") or dm_result.get("duplicate"))
    public_tried = bool(public)
    dm_tried = bool(private)
    public_complete = (not public_tried) or public_ok or bool(public_result.get("skipped"))
    dm_complete = (not dm_tried) or dm_ok or bool(dm_result.get("skipped"))
    reply_id = str(public_result.get("reply_id") or dm_result.get("reply_id") or "")
    from services.billing.membership.economy_policy import comment_outcome_units

    units = comment_outcome_units(
        comment_mode=plan.comment_mode,
        public_ok=public_ok if public_tried else False,
        dm_ok=dm_ok if dm_tried else False,
    )
    accepted = billable and units > 0
    _settle_comment_send(
        binding=binding,
        comment_id=comment_id,
        inbound_event_id=inbound_event_id,
        reply_id=reply_id,
        accepted=accepted,
        billable=billable,
        units=units if billable else 0,
    )
    await _maybe_send_resources(
        rule_decision=rule_decision,
        binding=binding,
        comment_id=comment_id,
        simulation=False,
        capture_send=None,
    )
    if public_complete and dm_complete:
        if public_tried and dm_tried:
            return CommentReplyResult(status="sent_comment_and_dm", reply_id=reply_id)
        if dm_tried and not public_tried:
            return CommentReplyResult(status="sent_dm", reply_id=reply_id)
        return CommentReplyResult(status="sent", reply_id=reply_id)
    if public_complete and public_tried:
        return CommentReplyResult(status="sent", reply_id=reply_id, reason="dm_incomplete")
    if dm_complete and dm_tried:
        return CommentReplyResult(status="sent_dm", reply_id=reply_id, reason="public_incomplete")
    return CommentReplyResult(status="failed", reason="comment_and_dm_both_failed")


async def _maybe_send_resources(
    *,
    rule_decision: Any,
    binding: Any,
    comment_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
) -> None:
    if rule_decision is None:
        return
    from services.integrations.meta.meta_comment_resource_send import send_comment_rule_resources

    await send_comment_rule_resources(
        tenant_id=str(getattr(binding, "tenant_id", "") or ""),
        rule_decision=rule_decision,
        comment_id=comment_id,
        channel=str(getattr(binding, "channel", "") or ""),
        binding_id=str(getattr(binding, "binding_id", "") or ""),
        simulation=simulation,
        capture_send=capture_send,
    )


def _settle_comment_send(
    *,
    binding: Any,
    comment_id: str,
    inbound_event_id: str | None,
    reply_id: str,
    accepted: bool,
    billable: bool = True,
    units: int | None = None,
) -> None:
    from services.brain.billing import settle_after_send

    tenant_id = str(getattr(binding, "tenant_id", "") or "")
    extras = [
        str(inbound_event_id or ""),
        str(comment_id or ""),
        str(getattr(binding, "conversation_id", "") or ""),
    ]
    settle_after_send(
        tenant_id=tenant_id,
        operation_id=str(comment_id or inbound_event_id or extras[2] or ""),
        accepted=bool(accepted and billable),
        channel="meta_comment",
        provider_message_id=reply_id,
        extra_ids=extras,
        units=0 if not billable else units,
    )
