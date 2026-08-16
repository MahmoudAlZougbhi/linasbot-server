"""Deterministic comment+DM rule handling (simulation + live public-first)."""

from __future__ import annotations

import logging
from typing import Any

from services.cm.comment_rules import CommentRuleDecision
from services.meta_app_registry import MetaAssetBinding

_runtime_logger = logging.getLogger("uvicorn.error")


def apply_comment_and_dm_rule(
    *,
    rule_decision: CommentRuleDecision,
    binding: MetaAssetBinding,
    comment_id: str,
    simulation: bool,
    capture_send: list[dict[str, Any]] | None,
) -> Any:
    """Return a result for simulation, or a follow-up decision for the live public path."""
    from services.meta_comment_replies import CommentReplyResult, _mark_sent_reply

    public_text = (rule_decision.reply_text or "").strip()
    dm_text = (rule_decision.dm_text or "").strip()
    if simulation:
        if capture_send is not None:
            if public_text:
                capture_send.append(
                    {
                        "comment_id": comment_id,
                        "channel": binding.channel,
                        "message": public_text,
                        "delivery": "public_reply",
                        "rule_id": rule_decision.rule_id,
                    }
                )
            if dm_text:
                capture_send.append(
                    {
                        "comment_id": comment_id,
                        "channel": binding.channel,
                        "message": dm_text,
                        "delivery": "private_reply",
                        "rule_id": rule_decision.rule_id,
                    }
                )
        _mark_sent_reply(binding, comment_id)
        return CommentReplyResult(status="simulated", reply_id="simulated_both")
    _runtime_logger.warning(
        "[meta-comment] comment_and_dm_second_send_blocked reason=single_primary_reply_purpose"
    )
    if public_text:
        return CommentRuleDecision(
            action="reply_comment",
            reply_text=public_text,
            rule_id=rule_decision.rule_id,
            reason=rule_decision.reason,
            policy_text=rule_decision.policy_text,
            matched=True,
            rule_mode=rule_decision.rule_mode,
            rule_revision=rule_decision.rule_revision,
            trigger_matched=rule_decision.trigger_matched,
            scope=rule_decision.scope,
            dm_text=dm_text,
            conflict_event="comment_and_dm_live_second_send_blocked",
        )
    return CommentRuleDecision(
        action="reply_dm",
        reply_text=dm_text,
        rule_id=rule_decision.rule_id,
        reason=rule_decision.reason,
        policy_text=rule_decision.policy_text,
        matched=True,
        rule_mode=rule_decision.rule_mode,
        rule_revision=rule_decision.rule_revision,
        trigger_matched=rule_decision.trigger_matched,
        scope=rule_decision.scope,
        dm_text=dm_text,
        conflict_event="comment_and_dm_live_second_send_blocked",
    )
