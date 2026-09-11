"""Static private-DM comment rules. AI DM modes must not use this path."""

from __future__ import annotations

import asyncio
from typing import Any

from services.cm.comment_rules import CommentRuleDecision
from services.meta_app_registry import MetaAssetBinding
from services.meta_comment_rule_modes import is_static_comment_dm, static_dm_text


async def maybe_handle_static_dm(
    *,
    rule_decision: CommentRuleDecision,
    binding: MetaAssetBinding,
    comment_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
    inbound_event_id: str | None = None,
    token: str = "",
    graph_api_version: str = "v24.0",
    client: Any | None = None,
) -> Any:
    from services.meta_comment_replies import CommentReplyResult, _mark_sent_reply, _provider_rejection_is_definitive

    if not is_static_comment_dm(rule_decision):
        return CommentReplyResult(status="skipped", reason="not_static_dm")
    dm_text = static_dm_text(rule_decision)
    if not dm_text:
        return CommentReplyResult(status="skipped", reason="comment_rule_dm_template_required")
    if simulation:
        payload = {
            "comment_id": comment_id,
            "channel": binding.channel,
            "message": dm_text,
            "delivery": "private_reply",
            "rule_id": rule_decision.rule_id,
        }
        if capture_send is not None:
            capture_send.append(payload)
        _mark_sent_reply(binding, comment_id)
        return CommentReplyResult(status="simulated", reply_id="simulated_dm")
    from services.meta_comment_private_reply import send_comment_private_reply
    from services.meta_controlled_evidence import meta_evidence_surface
    from services.meta_outbound_attempts import (
        MetaOutboundAttemptDecision,
        begin_meta_outbound_attempt,
        finish_meta_outbound_attempt,
    )

    private_attempt: MetaOutboundAttemptDecision | None = None
    if inbound_event_id:
        private_attempt = await begin_meta_outbound_attempt(
            event_id=inbound_event_id,
            surface=meta_evidence_surface(kind="meta_comment", channel=binding.channel),
            binding_id=binding.binding_id,
        )
        if private_attempt.kind == "duplicate_suppressed":
            return CommentReplyResult(status="ignored", reason="already_replied")
        if private_attempt.kind == "needs_owner_action":
            return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")

    try:
        ok, reason, response = await send_comment_private_reply(
            client,
            binding=binding,
            comment_id=comment_id,
            message=dm_text,
            token=token,
            graph_api_version=graph_api_version,
        )
    except BaseException:
        if private_attempt is not None and private_attempt.kind == "send":
            task = asyncio.create_task(
                finish_meta_outbound_attempt(
                    private_attempt,
                    status="needs_owner_action",
                    safe_reason="provider_call_ambiguous",
                )
            )
            from services.async_safety_cleanup import await_safety_task

            await await_safety_task(task)
        raise
    if not ok:
        if private_attempt is not None and private_attempt.kind == "send":
            ambiguous = not _provider_rejection_is_definitive(reason)
            try:
                await finish_meta_outbound_attempt(
                    private_attempt,
                    status="needs_owner_action" if ambiguous else "definitive_failure",
                    safe_reason="accepted_without_provider_id" if ambiguous else "provider_rejected",
                )
            except BaseException:
                return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
            if ambiguous:
                return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
        return CommentReplyResult(status="failed", reason=f"private_reply:{reason}")
    reply_id = str(response.get("id") or response.get("message_id") or "").strip()
    if private_attempt is not None and private_attempt.kind == "send":
        try:
            await finish_meta_outbound_attempt(
                private_attempt,
                status="accepted",
                safe_reason="provider_accepted",
                provider_message_id=reply_id,
            )
        except BaseException:
            return CommentReplyResult(status="skipped", reason="ambiguous_needs_owner_action")
    _mark_sent_reply(binding, comment_id)
    return CommentReplyResult(status="sent_dm", reply_id=reply_id)
