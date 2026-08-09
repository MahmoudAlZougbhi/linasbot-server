"""Server-side restricted topic + handoff enforcement (not optional retrieval)."""

from __future__ import annotations

from typing import Any

from services.cm.runtime_pipeline import DEFAULT_REFUSE_TEMPLATES, _handoff_reply
from services.cm.schemas import ActionsSection, HandoffPolicy, RestrictedPolicy
from services.cm.structured_resolver import find_restricted_topic, resolve_handoff
from services.cm.version_store import load_published_content
from services.cm.query_interpreter import BOOKING_INTENT_RE, HUMAN_INTENT_RE


def _detect_booking_or_human(message: str) -> str | None:
    if HUMAN_INTENT_RE.search(message or ""):
        return "human"
    if BOOKING_INTENT_RE.search(message or ""):
        return "booking"
    return None


def enforce_restricted_and_handoff(
    *,
    tenant_id: str,
    message: str,
    response_language: str,
    explicit_gender: str | None = None,
) -> dict[str, Any] | None:
    """Return a stop decision dict if restricted/handoff applies; else None."""
    _pointer, sections = load_published_content(tenant_id)
    restricted_policy = RestrictedPolicy.model_validate(sections.get("restricted") or {})
    topic = find_restricted_topic(message, restricted_policy)
    if topic is not None:
        template = (getattr(topic, "refuse_template", "") or "").strip()
        reply = template or DEFAULT_REFUSE_TEMPLATES.get(response_language, DEFAULT_REFUSE_TEMPLATES["en"])
        return {
            "stop": True,
            "reply": reply,
            "reason": "restricted",
            "metadata": {"restricted_topic_id": topic.id},
        }

    from services.cm.actions import ACTION_HUMAN_HANDOFF, action_enabled

    handoff_intent = _detect_booking_or_human(message)
    actions_section = ActionsSection.model_validate(sections.get("actions") or {})
    if handoff_intent and action_enabled(actions_section, ACTION_HUMAN_HANDOFF):
        handoff_policy = HandoffPolicy.model_validate(sections.get("handoff") or {})
        gender = None
        if explicit_gender in {"men", "male", "man"}:
            gender = "male"
        elif explicit_gender in {"women", "female", "woman"}:
            gender = "female"
        resolution = resolve_handoff(handoff_policy, gender=gender)
        if resolution.destination_value:
            return {
                "stop": True,
                "reply": _handoff_reply(
                    resolution.destination_type or "whatsapp",
                    resolution.destination_value,
                    response_language,
                ),
                "reason": "handoff",
                "metadata": {
                    "handoff_intent": handoff_intent,
                    "destination_type": resolution.destination_type,
                    "matched_row_id": resolution.matched_row_id,
                },
            }
    return None
