"""Classify published Comment Rule decisions for Meta ingress."""

from __future__ import annotations

from typing import Any

_DM_AFTER_PUBLIC = frozenset({"static_dm", "static_both", "ai_dm", "ai_both"})
_STATIC_DM = frozenset({"static_dm"})
_STATIC_BOTH = frozenset({"static_both"})
_STATIC_PUBLIC = frozenset({"static_comment"})


def _mode(rule_decision: Any) -> str:
    return str(getattr(rule_decision, "rule_mode", "") or "").strip().lower()


def _action(rule_decision: Any) -> str:
    return str(getattr(rule_decision, "action", "") or "").strip().lower()


def allows_private_after_public_reply(rule_decision: Any) -> bool:
    if rule_decision is None:
        return False
    mode = _mode(rule_decision)
    if mode in _DM_AFTER_PUBLIC:
        return True
    return mode == "deterministic" and _action(rule_decision) in {"reply_dm", "reply_comment_and_dm"}


def is_static_comment_dm(rule_decision: Any) -> bool:
    if rule_decision is None:
        return False
    mode = _mode(rule_decision)
    if mode in _STATIC_DM:
        return True
    return _action(rule_decision) == "reply_dm" and mode == "deterministic"


def is_static_both_comment(rule_decision: Any) -> bool:
    if rule_decision is None:
        return False
    mode = _mode(rule_decision)
    if mode in _STATIC_BOTH:
        return True
    return _action(rule_decision) == "reply_comment_and_dm" and mode == "deterministic"


def is_static_public_comment(rule_decision: Any) -> bool:
    if rule_decision is None:
        return False
    text = str(getattr(rule_decision, "reply_text", "") or "").strip()
    if not text:
        return False
    mode = _mode(rule_decision)
    if mode in _STATIC_PUBLIC:
        return True
    return (
        mode == "deterministic"
        and _action(rule_decision) == "reply_comment"
        and bool(getattr(rule_decision, "matched", False))
    )


def static_dm_text(rule_decision: Any) -> str:
    return str(getattr(rule_decision, "dm_text", "") or getattr(rule_decision, "reply_text", "") or "").strip()
