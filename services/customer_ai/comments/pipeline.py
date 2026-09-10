"""Seven Comment Rule modes. Manual/ignore never call the planner."""

from __future__ import annotations

from services.cm.comment_rules import evaluate_comment_rules, load_published_comments_section
from services.customer_ai.comment_normalize import normalize_comment_mode
from services.customer_ai.contracts.enums import CommentMode
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult


def winning_comment_mode(
    *,
    tenant_id: str,
    comment_text: str,
    post_id: str = "",
    channel: str = "",
) -> tuple[CommentMode | None, object]:
    section = load_published_comments_section(tenant_id)
    if section is None:
        return None, None
    decision = evaluate_comment_rules(section, comment_text=comment_text, post_id=post_id, channel=channel)
    if not decision.matched:
        return None, decision
    already = str(getattr(decision, "rule_mode", "") or "")
    if already in {
        "ignore",
        "static_comment",
        "static_dm",
        "static_both",
        "ai_comment",
        "ai_dm",
        "ai_both",
    }:
        return already, decision  # type: ignore[return-value]
    mode = normalize_comment_mode(
        action=decision.action,
        rule_mode=decision.rule_mode,
        ai_action_mode="",
    )
    return mode, decision


def deterministic_comment_result(mode: CommentMode, decision: object) -> TurnResult | None:
    public = str(getattr(decision, "reply_text", "") or "")
    private = str(getattr(decision, "dm_text", "") or "")
    rule_id = str(getattr(decision, "rule_id", "") or "")
    extra = {"path": "comment_rule", "rule_id": rule_id, "comment_mode": mode}
    if mode == "ignore":
        return TurnResult(
            stop_reason="policy_suppressed",
            envelope=FinalReplyEnvelope(decision="no_reply", dispositions={"comment": "policy_suppressed"}),
            extra=extra,
        )
    messages: list[OutboundMessage] = []
    if mode in {"static_comment", "static_both"} and public:
        messages.append(OutboundMessage(destination="comment", text=public, protected=True, component_id="public"))
    if mode in {"static_dm", "static_both"} and private:
        messages.append(OutboundMessage(destination="dm", text=private, protected=True, component_id="private"))
    if mode.startswith("static"):
        if not messages:
            return TurnResult(
                stop_reason="policy_suppressed",
                envelope=FinalReplyEnvelope(decision="no_reply"),
                extra=extra,
            )
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="deterministic",
                messages=messages,
                used_evidence_ids=[f"comment_rule:{rule_id}"],
                dispositions={"comment": "policy_suppressed"},
            ),
            extra=extra,
        )
    return None
