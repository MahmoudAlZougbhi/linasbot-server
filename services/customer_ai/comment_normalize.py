"""Normalize saved Comment Rule actions into the seven contract modes."""

from __future__ import annotations

from typing import Any

from services.customer_ai.contracts.enums import CommentMode

_STATIC_ACTIONS = {
    "reply_comment_static": "static_comment",
    "send_dm_static": "static_dm",
    "reply_comment_and_dm_static": "static_both",
}
_AI_ACTIONS = {
    "reply_comment": "ai_comment",
    "reply_dm": "ai_dm",
    "send_dm": "ai_dm",
    "reply_comment_and_dm": "ai_both",
}
_AI_ACTION_MODE = {
    "reply_comment": "ai_comment",
    "send_dm": "ai_dm",
    "reply_dm": "ai_dm",
    "reply_comment_and_dm": "ai_both",
}


def normalize_comment_mode(
    *,
    action: str = "",
    rule_mode: str = "",
    ai_action_mode: str = "",
) -> CommentMode | None:
    raw_action = (action or "").strip().lower()
    mode = (rule_mode or "").strip().lower()
    if raw_action in {"ignore", "skip", "no_reply"}:
        return "ignore"
    if raw_action in _STATIC_ACTIONS:
        return _STATIC_ACTIONS[raw_action]  # type: ignore[return-value]
    if mode == "deterministic" and raw_action in {
        "reply_comment",
        "reply_dm",
        "reply_comment_and_dm",
        "send_dm",
    }:
        return {
            "reply_comment": "static_comment",
            "reply_dm": "static_dm",
            "send_dm": "static_dm",
            "reply_comment_and_dm": "static_both",
        }[raw_action]  # type: ignore[return-value]
    if mode == "ai_guidance":
        mapped = _AI_ACTION_MODE.get((ai_action_mode or "").strip().lower()) or _AI_ACTIONS.get(raw_action)
        return mapped  # type: ignore[return-value]
    if raw_action in _AI_ACTIONS:
        return _AI_ACTIONS[raw_action]  # type: ignore[return-value]
    return None


def normalize_rule_dict(rule: dict[str, Any]) -> CommentMode | None:
    return normalize_comment_mode(
        action=str(rule.get("action") or ""),
        rule_mode=str(rule.get("rule_mode") or ""),
        ai_action_mode=str(rule.get("ai_action_mode") or ""),
    )
