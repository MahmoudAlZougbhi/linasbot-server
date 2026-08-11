"""Per-section quality: missing vs weak vs filled (real CM field heuristics)."""

from __future__ import annotations

from typing import Any, Literal

FillLevel = Literal["missing", "weak", "filled"]


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple)):
        return len(value) > 0
    return True


def _label_text(labels: Any) -> str:
    if not isinstance(labels, dict):
        return ""
    return " ".join(str(labels.get(k) or "") for k in ("ar", "en", "fr", "franco")).strip()


def _article_ok(item: dict[str, Any]) -> bool:
    return _nonempty(item.get("title")) and _nonempty(item.get("body"))


def _service_ok(item: dict[str, Any]) -> bool:
    return _nonempty(item.get("id")) and _nonempty(_label_text(item.get("labels")))


def _branch_ok(item: dict[str, Any]) -> bool:
    if not _nonempty(item.get("id")):
        return False
    if _nonempty(_label_text(item.get("labels"))):
        return True
    return _nonempty(item.get("address")) or _nonempty(item.get("street"))


def _hours_schedule_ok(item: dict[str, Any]) -> bool:
    days = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    for day in days:
        row = item.get(day)
        if not isinstance(row, dict):
            continue
        if row.get("closed") is True:
            return True
        if _nonempty(row.get("open")) and _nonempty(row.get("close")):
            return True
    return False


def _faq_item_ok(item: dict[str, Any]) -> bool:
    raw_variants = item.get("variants")
    variants: list[Any] = list(raw_variants) if isinstance(raw_variants, list) else []
    for v in variants:
        if not isinstance(v, dict):
            continue
        if _nonempty(v.get("question")) and _nonempty(v.get("answer")):
            return True
    return False


def _handoff_contact_ok(item: dict[str, Any]) -> bool:
    dest = str(item.get("destination_value") or item.get("phone_e164") or "").strip()
    return bool(dest)


def _prices_ok(payload: dict[str, Any]) -> bool:
    for key in ("catalog", "price_entries", "items", "discount_rules"):
        if isinstance(payload.get(key), list) and payload[key]:
            return True
    return _nonempty(payload.get("policy_text"))


def assess_section_fill(section: str, payload: dict[str, Any] | None, *, is_default: bool) -> dict[str, Any]:
    """Return fill level + gaps for one CM section (never invents sections)."""
    name = section.strip().replace("-", "_")

    # Comments policy is optional advanced control — empty defaults are intentional.
    if name == "comments":
        if is_default or not isinstance(payload, dict):
            return {
                "fill": "filled",
                "is_done": True,
                "gaps": [],
                "summary": "Optional — default AI comment behavior until you add keyword rules.",
            }
        gaps: list[str] = []
        rules = [it for it in (payload.get("rules") or []) if isinstance(it, dict)]
        for rule in rules:
            if rule.get("enabled") is False:
                continue
            has_match = bool(
                any(str(k).strip() for k in (rule.get("keywords") or []) if k is not None)
                or str(rule.get("pattern") or "").strip()
            )
            if not has_match:
                gaps.append("comment_rule_keywords_or_pattern")
                break
            action = str(rule.get("action") or "")
            if action == "reply_dm" and not str(rule.get("reply_template") or "").strip():
                gaps.append("comment_rule_dm_template")
                break
        if gaps:
            return {
                "fill": "weak",
                "is_done": False,
                "gaps": gaps,
                "summary": "Comment rules need match keywords/pattern (and DM template for reply_dm).",
            }
        return {
            "fill": "filled",
            "is_done": True,
            "gaps": [],
            "summary": "Filled enough to use — do not re-ask unless the owner explicitly wants changes.",
        }

    if is_default or not isinstance(payload, dict):
        return {
            "fill": "missing",
            "is_done": False,
            "gaps": ["no_owner_content"],
            "summary": "Still at factory default — not filled by the owner yet.",
        }

    gaps = []

    if name == "ai_basics":
        has_name = _nonempty(payload.get("clinic_name")) or _nonempty(payload.get("assistant_name"))
        has_role = any(
            _nonempty(payload.get(k)) for k in ("ai_role", "business_purpose", "short_introduction", "identity_summary")
        )
        if not has_name:
            gaps.append("business_or_assistant_name")
        if not has_role:
            gaps.append("role_or_purpose")
    elif name == "languages":
        if not _nonempty(payload.get("default_language")):
            gaps.append("default_language")
        langs = payload.get("supported_languages")
        if not isinstance(langs, (list, tuple)) or not langs:
            gaps.append("supported_languages")
    elif name == "style":
        if not any(_nonempty(payload.get(k)) for k in ("tone", "formality", "style_body", "response_length")):
            gaps.append("tone_or_style_body")
    elif name == "dynamic_messages":
        raw_items = payload.get("items")
        items: list[Any] = list(raw_items) if isinstance(raw_items, list) else []
        ok = any(isinstance(it, dict) and any(_nonempty(it.get(k)) for k in ("ar", "en", "fr", "name")) for it in items)
        if not ok and not _nonempty(payload.get("notes")):
            gaps.append("greeting_or_message_text")
    elif name == "services":
        items = [it for it in (payload.get("items") or []) if isinstance(it, dict)]
        if not any(_service_ok(it) for it in items):
            gaps.append("at_least_one_named_service")
    elif name == "branches":
        items = [it for it in (payload.get("items") or []) if isinstance(it, dict)]
        if items and not any(_branch_ok(it) for it in items):
            gaps.append("branch_name_or_address")
        elif not items and not _nonempty(payload.get("policy_text")) and not _nonempty(payload.get("notes")):
            gaps.append("locations_or_explicit_none")
    elif name == "opening_hours":
        items = [it for it in (payload.get("items") or []) if isinstance(it, dict)]
        if not any(_hours_schedule_ok(it) for it in items):
            gaps.append("named_schedule_with_hours")
    elif name == "prices":
        if not _prices_ok(payload):
            gaps.append("catalog_entries_or_policy")
    elif name in {"care", "knowledge"}:
        items = [it for it in (payload.get("items") or []) if isinstance(it, dict)]
        if not any(_article_ok(it) for it in items) and not _nonempty(payload.get("notes")):
            gaps.append("article_title_and_body")
    elif name == "faq":
        items = [it for it in (payload.get("items") or []) if isinstance(it, dict)]
        if not any(_faq_item_ok(it) for it in items):
            gaps.append("faq_question_and_answer")
    elif name == "handoff":
        contacts = [it for it in (payload.get("contacts") or []) if isinstance(it, dict)]
        if not any(_handoff_contact_ok(it) for it in contacts) and not _nonempty(payload.get("policy_text")):
            gaps.append("handoff_contact_destination")
    elif name == "restricted":
        # Empty topics + notes, or configured topics, both count as intentional.
        _raw_topics = payload.get("topics")
        topics: list[Any] = list(_raw_topics) if isinstance(_raw_topics, list) else []
        if topics:
            labeled = any(_nonempty(_label_text(it.get("labels"))) for it in topics if isinstance(it, dict))
            if not labeled:
                gaps.append("restricted_topic_labels")
        elif not _nonempty(payload.get("notes")):
            gaps.append("topics_or_explicit_none_note")
    elif name == "actions":
        _raw_action_items = payload.get("items")
        action_items: list[Any] = list(_raw_action_items) if isinstance(_raw_action_items, list) else []
        if not action_items:
            gaps.append("capability_toggles")
    elif name == "ai_limits":
        # Non-default payload already means owner touched limits — treat as filled unless empty junk.
        pass
    elif name == "off_days":
        _raw_rules = payload.get("rules")
        rules: list[Any] = list(_raw_rules) if isinstance(_raw_rules, list) else []
        if not rules and not _nonempty(payload.get("notes")):
            gaps.append("off_day_rules_or_note")
    else:
        gaps.append("unknown_section_shape")

    if gaps:
        return {
            "fill": "weak",
            "is_done": False,
            "gaps": gaps,
            "summary": "Has some content, but not enough for the AI to understand this part of the business correctly.",
        }
    return {
        "fill": "filled",
        "is_done": True,
        "gaps": [],
        "summary": "Filled enough to use — do not re-ask unless the owner explicitly wants changes.",
    }
