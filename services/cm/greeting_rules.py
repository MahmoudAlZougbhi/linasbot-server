"""Greeting rule normalization for CM dynamic_messages (backward compat)."""

from __future__ import annotations

from typing import Any, Literal

TriggerMode = Literal["always", "starts_with", "any_keyword", "session_start"]

_DEFAULT_TRIGGER: TriggerMode = "always"


def _text(value: object) -> str:
    return str(value or "").strip()


def normalize_greeting_item(raw: dict[str, Any]) -> dict[str, Any]:
    """Ensure legacy single-greeting items become valid multi-rule records."""
    item = dict(raw)
    if "enabled" not in item:
        item["enabled"] = True
    mode = _text(item.get("trigger_mode")) or _DEFAULT_TRIGGER
    if mode not in {"always", "starts_with", "any_keyword", "session_start"}:
        mode = _DEFAULT_TRIGGER
    item["trigger_mode"] = mode
    if "trigger_pattern" not in item:
        item["trigger_pattern"] = ""
    keywords = item.get("keywords")
    if not isinstance(keywords, list):
        item["keywords"] = []
    else:
        item["keywords"] = [k for k in (_text(x) for x in keywords) if k]
    if not _text(item.get("en")) and _text(item.get("notes")):
        item["en"] = _text(item.get("notes"))
    return item


def sanitize_dynamic_messages_payload(payload: dict[str, object]) -> dict[str, object]:
    """Normalize greeting rules on draft read/write."""
    out = dict(payload)
    raw_items = out.get("items")
    if not isinstance(raw_items, list):
        out["items"] = []
        return out
    normalized: list[dict[str, object]] = []
    for raw in raw_items:
        if isinstance(raw, dict):
            normalized.append(normalize_greeting_item(raw))
    out["items"] = normalized
    return out


def greeting_rule_has_text(item: dict[str, Any]) -> bool:
    return any(_text(item.get(k)) for k in ("ar", "en", "fr", "notes"))


def greeting_rule_trigger_ok(item: dict[str, Any]) -> bool:
    mode = _text(item.get("trigger_mode")) or _DEFAULT_TRIGGER
    if mode in {"always", "session_start"}:
        return True
    if mode == "starts_with":
        return bool(_text(item.get("trigger_pattern")))
    if mode == "any_keyword":
        keywords = item.get("keywords")
        return isinstance(keywords, list) and any(_text(k) for k in keywords)
    return False
