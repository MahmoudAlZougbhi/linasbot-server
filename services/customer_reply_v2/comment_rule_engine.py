"""V10 Comment Rule engine: post-specific override, priority, deterministic vs AI-guidance."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.customer_reply_v2.comment_rule_migrate import migrate_comment_rule, migrate_comments_section
from services.customer_reply_v2.comment_text_norm import normalize_comment_text
from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled

# Higher priority number wins. Tie-break is stable rule id (ascending).
PRIORITY_ORDER = "higher_number_wins"


@dataclass
class CommentEngineResult:
    matched: bool = False
    rule_mode: str = ""
    rule_id: str = ""
    rule_revision: int = 0
    scope: str = ""
    trigger_matched: str = ""
    action: str = ""
    reply_text: str = ""
    dm_text: str = ""
    policy_text: str = ""
    ai_guidance_rules: list[dict[str, Any]] = field(default_factory=list)
    conflict_event: str = ""
    mapping: list[dict[str, str]] = field(default_factory=list)
    reason: str = ""
    attachments: list[dict[str, Any]] = field(default_factory=list)


def _needles(rule: dict[str, Any]) -> list[str]:
    values = [str(k).strip() for k in (rule.get("keywords") or []) if str(k).strip()]
    pattern = str(rule.get("pattern") or "").strip()
    if pattern and pattern not in values:
        values.append(pattern)
    return [normalize_comment_text(v) for v in values if normalize_comment_text(v)]


def trigger_matches(rule: dict[str, Any], comment_text: str) -> str:
    trigger = str(rule.get("trigger_type") or "contains_any").strip().lower()
    hay = normalize_comment_text(comment_text)
    if trigger == "all_comments":
        return "all_comments"
    needles = _needles(rule)
    if not needles:
        return ""
    if trigger == "exact_text":
        return "exact_text" if hay == needles[0] else ""
    if trigger == "contains_all":
        return "contains_all" if all(n in hay for n in needles) else ""
    if any(n in hay for n in needles):
        return trigger if trigger in {"contains_any", "keyword_set"} else "contains_any"
    return ""


def _wanted_post_ids(rule: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    raw_ids = rule.get("post_ids")
    if isinstance(raw_ids, list):
        for raw in raw_ids:
            value = str(raw or "").strip()
            if value and value not in ids:
                ids.append(value)
    single = str(rule.get("post_id") or "").strip()
    if single and single not in ids:
        ids.append(single)
    return ids


def _scope_ok(rule: dict[str, Any], *, post_id: str, account_id: str) -> bool:
    wanted = _wanted_post_ids(rule)
    scope = str(rule.get("scope") or "all_posts")
    if wanted:
        scope = "specific_post"
    if scope != "specific_post":
        return True
    if not wanted or str(post_id or "").strip() not in wanted:
        return False
    want_account = str(rule.get("connected_account_id") or rule.get("page_or_ig_account_id") or "").strip()
    if want_account and account_id and want_account != str(account_id or "").strip():
        return False
    return True


def _channel_ok(rule: dict[str, Any], channel: str) -> bool:
    want = str(rule.get("channel") or "any").strip().lower()
    if want in {"", "any"}:
        return True
    ch = (channel or "").strip().lower()
    if want == "facebook":
        return "facebook" in ch or ch in {"fb", "messenger"}
    if want == "instagram":
        return "instagram" in ch or ch == "ig"
    if want == "tiktok":
        return "tiktok" in ch
    return want == ch


def _sort_key(rule: dict[str, Any]) -> tuple[int, int, str]:
    scope_rank = 0 if str(rule.get("scope") or "") == "specific_post" else 1
    try:
        priority = int(rule.get("priority") or 0)
    except (TypeError, ValueError):
        priority = 0
    return (scope_rank, -priority, str(rule.get("id") or ""))


def _active(rule: dict[str, Any]) -> bool:
    if rule.get("enabled") is False:
        return False
    status = str(rule.get("status") or "").strip().lower()
    return status not in {"deleted", "archived", "inactive"}


def evaluate_comment_engine(
    section: dict[str, Any] | None,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
    account_id: str = "",
) -> CommentEngineResult:
    payload = dict(section or {})
    rules, mapping = migrate_comments_section(payload)
    policy_text = str(payload.get("policy_text") or "").strip()
    default_action = str(payload.get("default_action") or "reply_comment").strip()
    ordered = sorted([r for r in rules if _active(r)], key=_sort_key)
    result = CommentEngineResult(policy_text=policy_text, mapping=mapping, reason="default_action")

    for rule in ordered:
        if not _channel_ok(rule, channel) or not _scope_ok(rule, post_id=post_id, account_id=account_id):
            continue
        trigger = trigger_matches(rule, comment_text)
        if not trigger:
            continue
        if str(rule.get("rule_mode") or "") == "deterministic":
            action = str(rule.get("static_action") or rule.get("action") or "ignore")
            result.matched = True
            result.rule_mode = "deterministic"
            result.rule_id = str(rule.get("id") or "")
            result.rule_revision = int(rule.get("revision") or 1)
            result.scope = str(rule.get("scope") or "")
            result.trigger_matched = trigger
            result.action = action
            result.reply_text = str(rule.get("reply_template") or "").strip()
            result.dm_text = str(rule.get("dm_template") or "").strip() or (
                result.reply_text if action in {"send_dm_static", "reply_dm"} else ""
            )
            result.attachments = list(rule.get("attachments") or [])
            result.reason = f"rule_match:{result.rule_id}"
            return result

    guidance: list[dict[str, Any]] = []
    for rule in ordered:
        if str(rule.get("rule_mode") or "") != "ai_guidance":
            continue
        if not _channel_ok(rule, channel) or not _scope_ok(rule, post_id=post_id, account_id=account_id):
            continue
        trigger = trigger_matches(rule, comment_text)
        if not trigger:
            continue
        guidance.append({**rule, "trigger_matched": trigger})

    if guidance:
        actions = {str(g.get("ai_action_mode") or "reply_comment") for g in guidance}
        chosen = guidance
        conflict = ""
        if len(actions) > 1:
            chosen = [guidance[0]]
            conflict = "ai_action_conflict"
        result.matched = True
        result.rule_mode = "ai_guidance"
        result.rule_id = str(chosen[0].get("id") or "")
        result.rule_revision = int(chosen[0].get("revision") or 1)
        result.scope = str(chosen[0].get("scope") or "")
        result.trigger_matched = str(chosen[0].get("trigger_matched") or "")
        result.action = str(chosen[0].get("ai_action_mode") or "reply_comment")
        result.ai_guidance_rules = [
            {
                "id": str(g.get("id") or ""),
                "title": str(g.get("name") or g.get("id") or ""),
                "revision": int(g.get("revision") or 1),
                "scope": str(g.get("scope") or ""),
                "priority": int(g.get("priority") or 0),
                "ai_action_mode": str(g.get("ai_action_mode") or "reply_comment"),
                "ai_instructions": str(g.get("ai_instructions") or ""),
                "post_id": str(g.get("post_id") or ""),
                "post_ids": _wanted_post_ids(g),
                "attachments": list(g.get("attachments") or []),
            }
            for g in chosen
        ]
        result.conflict_event = conflict
        result.reason = f"ai_guidance:{result.rule_id}"
        return result

    result.action = default_action if default_action in {"reply_comment", "ignore"} else "reply_comment"
    result.matched = False
    return result


def evaluate_published_comment_engine(
    tenant_id: str,
    *,
    comment_text: str,
    channel: str = "",
    post_id: str = "",
    account_id: str = "",
) -> CommentEngineResult:
    from services.cm.version_store import PublishedVersionError, load_published_content

    try:
        _pointer, sections = load_published_content(tenant_id)
    except PublishedVersionError:
        payload: dict[str, Any] = {}
    else:
        raw = sections.get("comments")
        payload = dict(raw) if isinstance(raw, dict) else {}
    return evaluate_comment_engine(
        payload,
        comment_text=comment_text,
        channel=channel,
        post_id=post_id,
        account_id=account_id,
    )


def preview_comment_rule(
    rule: dict[str, Any],
    *,
    comment_text: str,
    post_id: str = "",
    channel: str = "",
    account_id: str = "",
) -> dict[str, Any]:
    migrated, mapping = migrate_comment_rule(dict(rule or {}))
    trigger = trigger_matches(migrated, comment_text)
    scoped = _scope_ok(migrated, post_id=post_id, account_id=account_id) and _channel_ok(migrated, channel)
    return {
        "matched": bool(trigger) and scoped and _active(migrated),
        "trigger_matched": trigger if scoped else "",
        "rule_mode": migrated.get("rule_mode"),
        "action": migrated.get("static_action") or migrated.get("ai_action_mode") or migrated.get("action"),
        "mapping": mapping,
        "priority_order": PRIORITY_ORDER,
        "v10": customer_ai_v10_runtime_enabled(),
    }
