"""Canonical WhatsApp template ids used by Live Chat logs and Cloud templates."""

from __future__ import annotations

LEGACY_TEMPLATE_ALIASES: dict[str, str] = {
    "post_session_feedback": "thank_you_message_sent_after_session",
    "twenty_day_followup": "sent_17_days_after_last_session_new",
    "one_month_followup": "sent_17_days_after_last_session_new",
    "missed_this_month": "sent_for_pause",
    "missed_paused_appointment": "sent_for_pause",
    "attended_yesterday": "session_feedback",
}


def normalize_template_id(template_id: str | None) -> str:
    """Return canonical template ID for legacy aliases."""
    if not template_id:
        return ""
    return LEGACY_TEMPLATE_ALIASES.get(template_id, template_id)
