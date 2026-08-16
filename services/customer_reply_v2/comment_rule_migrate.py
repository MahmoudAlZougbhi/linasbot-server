"""Backward-compatible mapping from legacy Comment Rules to V10 fields.

Keeps rule IDs. Does not delete old rules. Returns a mapping note per rule.
"""

from __future__ import annotations

from typing import Any

LEGACY_TO_V10_ACTIONS = {
    "ignore": "ignore",
    "reply_comment": "reply_comment_static",
    "reply_dm": "send_dm_static",
    "reply_comment_and_dm": "reply_comment_and_dm_static",
}


def migrate_comment_rule(raw: dict[str, Any]) -> tuple[dict[str, Any], str]:
    rule = dict(raw or {})
    notes: list[str] = []
    if str(rule.get("post_id") or "").strip():
        rule["scope"] = "specific_post"
        notes.append("scope:specific_post")
    elif not str(rule.get("scope") or "").strip():
        rule["scope"] = "all_posts"
        notes.append("scope:all_posts")
    template = str(rule.get("reply_template") or "").strip()
    action = str(rule.get("action") or "reply_comment").strip()
    if not str(rule.get("rule_mode") or "").strip():
        if action == "ignore" or template:
            rule["rule_mode"] = "deterministic"
            notes.append("mode:deterministic")
        else:
            rule["rule_mode"] = "ai_guidance"
            notes.append("mode:ai_guidance")
    if not str(rule.get("trigger_type") or "").strip():
        match_mode = str(rule.get("match_mode") or "any_keyword").strip().lower()
        if match_mode == "contains":
            rule["trigger_type"] = "contains_any"
        elif match_mode == "regex":
            rule["trigger_type"] = "contains_any"
            if not any(str(k).strip() for k in (rule.get("keywords") or [])) and str(rule.get("pattern") or "").strip():
                rule["keywords"] = [str(rule.get("pattern") or "").strip()]
            notes.append("regex_to_contains_any")
        else:
            rule["trigger_type"] = "keyword_set"
        notes.append(f"trigger:{rule['trigger_type']}")
    try:
        rule["priority"] = int(rule.get("priority") or 0)
    except (TypeError, ValueError):
        rule["priority"] = 0
    try:
        rule["revision"] = int(rule.get("revision") or 1)
    except (TypeError, ValueError):
        rule["revision"] = 1
    if rule.get("rule_mode") == "deterministic" and action in LEGACY_TO_V10_ACTIONS:
        if action != "ignore" and template:
            rule["static_action"] = LEGACY_TO_V10_ACTIONS[action]
        elif action == "ignore":
            rule["static_action"] = "ignore"
        else:
            rule["static_action"] = "ignore"
    if rule.get("rule_mode") == "ai_guidance":
        rule["ai_action_mode"] = str(rule.get("ai_action_mode") or _legacy_ai_action(action))
        if not str(rule.get("ai_instructions") or "").strip():
            rule["ai_instructions"] = str(rule.get("notes") or "").strip()
    if not str(rule.get("dm_template") or "").strip() and action in {"reply_dm", "reply_comment_and_dm"}:
        rule["dm_template"] = template
    return rule, ",".join(notes) or "unchanged"


def migrate_comments_section(payload: dict[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    section = dict(payload or {})
    mapping: list[dict[str, str]] = []
    rules: list[dict[str, Any]] = []
    for raw in section.get("rules") or []:
        if not isinstance(raw, dict):
            continue
        migrated, note = migrate_comment_rule(raw)
        rules.append(migrated)
        mapping.append({"id": str(migrated.get("id") or ""), "mapping": note})
    return rules, mapping


def _legacy_ai_action(action: str) -> str:
    if action == "reply_dm":
        return "send_dm"
    if action == "reply_comment_and_dm":
        return "reply_comment_and_dm"
    return "reply_comment"
