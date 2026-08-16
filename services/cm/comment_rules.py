"""Evaluate published CM Comments rules for Meta comment events.

V10 engine: post-specific override, higher priority wins, deterministic vs AI-guidance.
Rollback: CUSTOMER_AI_V10_RUNTIME=false restores list-order matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from services.cm.schemas import CommentRule, CommentsSection
from services.cm.version_store import PublishedVersionError, load_published_content
from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled

CommentAction = Literal["reply_comment", "reply_dm", "ignore", "reply_comment_and_dm"]


@dataclass(frozen=True)
class CommentRuleDecision:
    action: CommentAction
    reply_text: str = ""
    rule_id: str = ""
    reason: str = ""
    policy_text: str = ""
    matched: bool = False
    rule_mode: str = ""
    rule_revision: int = 0
    trigger_matched: str = ""
    scope: str = ""
    dm_text: str = ""
    ai_guidance_rules: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    conflict_event: str = ""


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


def _wanted_post_ids(rule: CommentRule) -> list[str]:
    ids: list[str] = []
    for raw in getattr(rule, "post_ids", None) or []:
        value = str(raw or "").strip()
        if value and value not in ids:
            ids.append(value)
    single = (rule.post_id or "").strip()
    if single and single not in ids:
        ids.append(single)
    return ids


def _post_ok(rule: CommentRule, post_id: str) -> bool:
    wanted = _wanted_post_ids(rule)
    if not wanted:
        return True
    return (post_id or "").strip() in wanted


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
    trigger = str(getattr(rule, "trigger_type", "") or "").strip().lower()
    if trigger == "all_comments":
        return True
    mode = (rule.match_mode or "any_keyword").strip().lower()
    if mode == "regex":
        return bool((rule.pattern or "").strip())
    return bool(any(str(k).strip() for k in rule.keywords) or (rule.pattern or "").strip())


def _legacy_evaluate(
    section: CommentsSection | None,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
) -> CommentRuleDecision:
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
        if action not in {"reply_comment", "reply_dm", "ignore", "reply_comment_and_dm"}:
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


def _action_from_engine(action: str) -> CommentAction:
    if action in {"ignore"}:
        return "ignore"
    if action in {"send_dm_static", "reply_dm", "send_dm"}:
        return "reply_dm"
    if action in {"reply_comment_and_dm_static", "reply_comment_and_dm"}:
        return "reply_comment_and_dm"
    return "reply_comment"


def evaluate_comment_rules(
    section: CommentsSection | None,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
    account_id: str = "",
) -> CommentRuleDecision:
    """Post-specific + higher priority wins when V10 is on. Else first list match."""
    if not customer_ai_v10_runtime_enabled():
        return _legacy_evaluate(section, comment_text=comment_text, channel=channel, post_id=post_id)
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    payload = (section or CommentsSection()).model_dump(mode="json")
    engine = evaluate_comment_engine(
        payload,
        comment_text=comment_text,
        channel=channel,
        post_id=post_id,
        account_id=account_id,
    )
    if engine.rule_mode == "ai_guidance":
        return CommentRuleDecision(
            action="reply_comment",
            reply_text="",
            rule_id=engine.rule_id,
            reason=engine.reason,
            policy_text=engine.policy_text,
            matched=True,
            rule_mode="ai_guidance",
            rule_revision=engine.rule_revision,
            trigger_matched=engine.trigger_matched,
            scope=engine.scope,
            dm_text="",
            ai_guidance_rules=tuple(engine.ai_guidance_rules),
            conflict_event=engine.conflict_event,
        )
    return CommentRuleDecision(
        action=_action_from_engine(engine.action),
        reply_text=engine.reply_text,
        rule_id=engine.rule_id,
        reason=engine.reason,
        policy_text=engine.policy_text,
        matched=engine.matched,
        rule_mode=engine.rule_mode,
        rule_revision=engine.rule_revision,
        trigger_matched=engine.trigger_matched,
        scope=engine.scope,
        dm_text=engine.dm_text,
        ai_guidance_rules=tuple(engine.ai_guidance_rules),
        conflict_event=engine.conflict_event,
    )


def evaluate_published_comment_rules(
    tenant_id: str,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
    account_id: str = "",
) -> CommentRuleDecision:
    section = load_published_comments_section(tenant_id)
    return evaluate_comment_rules(
        section,
        comment_text=comment_text,
        channel=channel,
        post_id=post_id,
        account_id=account_id,
    )


def decision_to_dict(decision: CommentRuleDecision) -> dict[str, Any]:
    return {
        "action": decision.action,
        "reply_text": decision.reply_text,
        "rule_id": decision.rule_id,
        "reason": decision.reason,
        "policy_text": decision.policy_text,
        "matched": decision.matched,
        "rule_mode": decision.rule_mode,
        "rule_revision": decision.rule_revision,
        "trigger_matched": decision.trigger_matched,
        "scope": decision.scope,
        "dm_text": decision.dm_text,
        "ai_guidance_rules": list(decision.ai_guidance_rules),
        "conflict_event": decision.conflict_event,
    }
