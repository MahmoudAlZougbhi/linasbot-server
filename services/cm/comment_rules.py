"""Evaluate published CM Comments rules for Meta comment events.

Deterministic match → action. No silent fallback from reply_dm to public reply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from services.cm.schemas import CommentRule, CommentsSection
from services.cm.version_store import PublishedVersionError, load_published_content

CommentAction = Literal["reply_comment", "reply_dm", "ignore"]


@dataclass(frozen=True)
class CommentRuleDecision:
    action: CommentAction
    reply_text: str = ""
    rule_id: str = ""
    reason: str = ""
    policy_text: str = ""
    matched: bool = False


def load_published_comments_section(tenant_id: str) -> CommentsSection | None:
    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        return None
    raw = sections.get("comments")
    if not isinstance(raw, dict):
        return CommentsSection()
    try:
        return CommentsSection.model_validate(raw)
    except Exception:
        return CommentsSection()


def _channel_ok(rule: CommentRule, channel: str) -> bool:
    want = (rule.channel or "any").strip().lower()
    if want in {"", "any"}:
        return True
    return want == (channel or "").strip().lower()


def _post_ok(rule: CommentRule, post_id: str) -> bool:
    want = (rule.post_id or "").strip()
    if not want:
        return True
    return want == (post_id or "").strip()


def _text_matches(rule: CommentRule, text: str) -> bool:
    hay = (text or "").strip().lower()
    if not hay:
        return False
    mode = (rule.match_mode or "any_keyword").strip().lower()
    if mode == "contains":
        needles = [k.strip().lower() for k in rule.keywords if str(k).strip()]
        if not needles and (rule.pattern or "").strip():
            needles = [(rule.pattern or "").strip().lower()]
        return any(n in hay for n in needles)
    if mode == "regex":
        pattern = (rule.pattern or "").strip()
        if not pattern:
            return False
        try:
            return re.search(pattern, text or "", flags=re.IGNORECASE) is not None
        except re.error:
            return False
    keywords = [k.strip().lower() for k in rule.keywords if str(k).strip()]
    if not keywords:
        return False
    return any(k in hay for k in keywords)


def rule_is_matchable(rule: CommentRule) -> bool:
    if not rule.enabled:
        return False
    mode = (rule.match_mode or "any_keyword").strip().lower()
    if mode == "regex":
        return bool((rule.pattern or "").strip())
    return bool(any(str(k).strip() for k in rule.keywords) or (rule.pattern or "").strip())


def evaluate_comment_rules(
    section: CommentsSection | None,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
) -> CommentRuleDecision:
    """First matching enabled rule wins (list order). Else default_action."""
    policy = section or CommentsSection()
    policy_text = (policy.policy_text or "").strip()

    for rule in policy.rules:
        if not rule_is_matchable(rule):
            continue
        if not _channel_ok(rule, channel):
            continue
        if not _post_ok(rule, post_id):
            continue
        if not _text_matches(rule, comment_text):
            continue
        action: CommentAction = rule.action  # type: ignore[assignment]
        if action not in {"reply_comment", "reply_dm", "ignore"}:
            action = "reply_comment"
        return CommentRuleDecision(
            action=action,
            reply_text=(rule.reply_template or "").strip(),
            rule_id=rule.id,
            reason=f"rule_match:{rule.id}",
            policy_text=policy_text,
            matched=True,
        )

    default: CommentAction = policy.default_action  # type: ignore[assignment]
    if default not in {"reply_comment", "ignore"}:
        default = "reply_comment"
    return CommentRuleDecision(
        action=default,
        reply_text="",
        rule_id="",
        reason="default_action",
        policy_text=policy_text,
        matched=False,
    )


def evaluate_published_comment_rules(
    tenant_id: str,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
) -> CommentRuleDecision:
    section = load_published_comments_section(tenant_id)
    return evaluate_comment_rules(
        section,
        comment_text=comment_text,
        channel=channel,
        post_id=post_id,
    )


def decision_to_dict(decision: CommentRuleDecision) -> dict[str, Any]:
    return {
        "action": decision.action,
        "reply_text": decision.reply_text,
        "rule_id": decision.rule_id,
        "reason": decision.reason,
        "policy_text": decision.policy_text,
        "matched": decision.matched,
    }
