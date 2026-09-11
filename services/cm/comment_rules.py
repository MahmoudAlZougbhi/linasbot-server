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
    attachments: tuple[dict[str, Any], ...] = field(default_factory=tuple)


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
    for post in getattr(rule, "selected_posts", None) or []:
        if isinstance(post, dict):
            value = str(post.get("id") or "").strip()
        else:
            value = str(getattr(post, "id", "") or "").strip()
        if value and value not in ids:
            ids.append(value)
    return ids


def _post_ok(rule: CommentRule, post_id: str) -> bool:
    wanted = _wanted_post_ids(rule)
    if not wanted:
        return True
    return (post_id or "").strip() in wanted


def _trigger_all_comments(rule: CommentRule) -> bool:
    return str(getattr(rule, "trigger_type", "") or "").strip().lower() == "all_comments"


def _text_matches(rule: CommentRule, text: str) -> bool:
    if _trigger_all_comments(rule):
        return True
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


def _attachment_rows(rule: CommentRule) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for item in getattr(rule, "attachments", None) or []:
        if hasattr(item, "model_dump"):
            rows.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            rows.append(dict(item))
    return tuple(rows)


def _destination_action(rule: CommentRule) -> CommentAction:
    raw = str(rule.action or "").strip().lower()
    mapped = {
        "ignore": "ignore",
        "reply_comment": "reply_comment",
        "reply_comment_static": "reply_comment",
        "reply_dm": "reply_dm",
        "send_dm": "reply_dm",
        "send_dm_static": "reply_dm",
        "reply_comment_and_dm": "reply_comment_and_dm",
        "reply_comment_and_dm_static": "reply_comment_and_dm",
    }.get(raw, "reply_comment")
    return mapped  # type: ignore[return-value]


def _specificity(rule: CommentRule) -> int:
    scope = str(getattr(rule, "scope", "") or "").strip().lower()
    if scope == "specific_post" or _wanted_post_ids(rule):
        return 1
    return 0


def _pick_winner(matches: list[CommentRule]) -> CommentRule:
    best = max((_specificity(rule), int(getattr(rule, "priority", 0) or 0)) for rule in matches)
    finalists = [rule for rule in matches if (_specificity(rule), int(getattr(rule, "priority", 0) or 0)) == best]
    return sorted(finalists, key=lambda rule: str(rule.id or ""))[0]


def _decision_from_rule(section: CommentsSection, rule: CommentRule) -> CommentRuleDecision:
    from services.customer_ai.comment_normalize import normalize_comment_mode

    mode = normalize_comment_mode(
        action=str(rule.action or ""),
        rule_mode=str(rule.rule_mode or ""),
        ai_action_mode=str(getattr(rule, "ai_action_mode", "") or ""),
    ) or str(rule.rule_mode or "")
    guidance: tuple[dict[str, Any], ...] = ()
    if mode in {"ai_comment", "ai_dm", "ai_both"}:
        guidance = (
            {
                "rule_id": rule.id,
                "ai_instructions": (rule.ai_instructions or "").strip(),
                "ai_action_mode": str(getattr(rule, "ai_action_mode", "") or ""),
            },
        )
    return CommentRuleDecision(
        action=_destination_action(rule),
        reply_text=(rule.reply_template or "").strip(),
        rule_id=rule.id,
        reason=f"rule_match:{rule.id}",
        policy_text=(section.policy_text or "").strip(),
        matched=True,
        rule_mode=str(mode or ""),
        rule_revision=int(getattr(rule, "revision", 1) or 1),
        trigger_matched=str(getattr(rule, "trigger_type", "") or ""),
        scope=str(getattr(rule, "scope", "") or ""),
        dm_text=(rule.dm_template or "").strip(),
        ai_guidance_rules=guidance,
        attachments=_attachment_rows(rule),
    )


def evaluate_comment_rules(
    section: CommentsSection | None,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
    account_id: str = "",
) -> CommentRuleDecision:
    """Winning published rule: post-specific, then priority, then stable rule id."""
    _ = account_id
    policy = section or CommentsSection()
    matches: list[CommentRule] = []
    for rule in policy.rules:
        if not rule_is_matchable(rule):
            continue
        if not _channel_ok(rule, channel):
            continue
        if not _post_ok(rule, post_id):
            continue
        if not _text_matches(rule, comment_text):
            continue
        matches.append(rule)
    if not matches:
        return _legacy_evaluate(policy, comment_text=comment_text, channel=channel, post_id=post_id)
    return _decision_from_rule(policy, _pick_winner(matches))


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
        "attachments": list(decision.attachments),
    }
