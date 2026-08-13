"""Server-side restricted topic + handoff enforcement (not optional retrieval)."""

from __future__ import annotations

from typing import Any

from services.cm.query_interpreter import BOOKING_INTENT_RE, HUMAN_INTENT_RE
from services.cm.runtime_pipeline import DEFAULT_REFUSE_TEMPLATES, _handoff_reply
from services.cm.schemas import HandoffPolicy, RestrictedPolicy
from services.cm.structured_resolver import find_restricted_topic, resolve_handoff
from services.cm.version_store import load_published_content


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
    channel: str | None = None,
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

    from services.cm.capability_gates import human_handoff_enabled
    from services.requests.capture import (
        comment_capture_policy_reply,
        is_public_comment_channel,
        public_comment_dm_invite,
        skip_forced_booking_wa_me,
    )
    from services.requests.intent import is_appointment_or_order_intent

    # Exact public-comment channels only — never substring-match (comment_linked_dm is private).
    public_comment = is_public_comment_channel(channel)
    handoff_intent = _detect_booking_or_human(message)
    if handoff_intent == "booking" and skip_forced_booking_wa_me(tenant_id):
        if public_comment:
            return comment_capture_policy_reply(
                tenant_id=tenant_id,
                message=message,
                response_language=response_language,
                booking_or_order_intent=True,
            )
        # DM/private (incl. comment_linked_dm): let Requests capture AI continue (no forced wa.me).
        return None
    if public_comment and skip_forced_booking_wa_me(tenant_id) and is_appointment_or_order_intent(message):
        return comment_capture_policy_reply(
            tenant_id=tenant_id,
            message=message,
            response_language=response_language,
            booking_or_order_intent=True,
        )

    if handoff_intent and human_handoff_enabled(tenant_id):
        # Public comments must never receive phone / wa.me / email destinations.
        if public_comment:
            return {
                "stop": True,
                "reply": public_comment_dm_invite(response_language),
                "reason": "handoff_public_comment_dm_invite",
                "metadata": {
                    "handoff_intent": handoff_intent,
                    "pii_safe_public_comment": True,
                },
            }
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
