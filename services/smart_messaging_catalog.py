"""
Smart Messaging template catalog and scheduling defaults.
"""

from copy import deepcopy
from typing import Dict, Optional

# 17-day follow-up: canonical id matches Meta template name sent_17_days_after_last_session_new (3 body variables).
TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS = 17

DAILY_TEMPLATE_IDS = (
    "reminder_24h",
    "thank_you_message_sent_after_session",
    "session_feedback",
    "missed_yesterday",
    "sent_17_days_after_last_session_new",
)

CAMPAIGN_TEMPLATE_IDS = (
    "sent_for_pause",
    "whatsapp_lead_no_booking",
)

SUPPORTED_TEMPLATE_IDS = DAILY_TEMPLATE_IDS + CAMPAIGN_TEMPLATE_IDS

# Legacy IDs filtered out of UI/API lists; empty after removing same_day_checkin / no_show_followup.
DEPRECATED_TEMPLATE_IDS = ()

LEGACY_TEMPLATE_ALIASES = {
    "post_session_feedback": "thank_you_message_sent_after_session",
    "twenty_day_followup": "sent_17_days_after_last_session_new",
    "one_month_followup": "sent_17_days_after_last_session_new",
    "missed_this_month": "sent_for_pause",
    "missed_paused_appointment": "sent_for_pause",
    "attended_yesterday": "session_feedback",
}

TEMPLATE_METADATA: Dict[str, Dict[str, str]] = {
    "reminder_24h": {
        "name": "24-Hour Reminder",
        "description": "Daily fixed-time reminder for tomorrow appointments.",
    },
    "thank_you_message_sent_after_session": {
        "name": "thank_you_message_sent_after_session",
        "description": "Same calendar day, N hours after a completed (Done) visit — 1–5 star reply flow (Meta template name = internal id). Replies: Smart Messaging → Star ratings. Legacy internal id: post_session_feedback. Different from next-day Meta template session_feedback.",
    },
    "session_feedback": {
        "name": "session_feedback",
        "description": "Next-day after Done visit. WhatsApp Meta template name: session_feedback (1 body variable: customer_name; rating buttons on Meta). Legacy internal id attended_yesterday maps here.",
    },
    "missed_yesterday": {
        "name": "Missed Yesterday",
        "description": "Daily fixed-time follow-up for yesterday missed appointments (date=yesterday, status=Available).",
    },
    "sent_17_days_after_last_session_new": {
        "name": "sent_17_days_after_last_session_new",
        "description": "Daily fixed-time follow-up 17 days after last Done session. Meta template name (same as internal id): sent_17_days_after_last_session_new — 3 body variables: customer_name, branch_name, service_name. Legacy: twenty_day_followup, one_month_followup.",
    },
    "sent_for_pause": {
        "name": "sent_for_pause",
        "description": "Paused BOC campaign + end-of-month scheduler. Meta template name: sent_for_pause (1 body variable: customer_name). Legacy ids: missed_paused_appointment, missed_this_month.",
    },
    "whatsapp_lead_no_booking": {
        "name": "WhatsApp Lead (No CRM / No Booking)",
        "description": "Manual campaign for users who chatted on WhatsApp but have no BOC customer file and no appointments.",
    },
}

DEFAULT_TEMPLATE_SCHEDULES: Dict[str, Dict[str, object]] = {
    "reminder_24h": {
        "enabled": True,
        "sendTime": "15:00",
        "timezone": "Asia/Beirut",
    },
    "thank_you_message_sent_after_session": {
        "enabled": True,
        "sendTime": "20:00",
        "timezone": "Asia/Beirut",
        "delayHours": 3,
    },
    "session_feedback": {
        "enabled": True,
        "sendTime": "11:00",
        "timezone": "Asia/Beirut",
    },
    "missed_yesterday": {
        "enabled": True,
        "sendTime": "10:00",
        "timezone": "Asia/Beirut",
    },
    "sent_17_days_after_last_session_new": {
        "enabled": True,
        "sendTime": "14:00",
        "timezone": "Asia/Beirut",
    },
}


def normalize_template_id(template_id: Optional[str]) -> str:
    """Return canonical template ID for legacy aliases."""
    if not template_id:
        return ""
    return LEGACY_TEMPLATE_ALIASES.get(template_id, template_id)


def get_default_schedule(template_id: str) -> Dict[str, object]:
    """Get schedule defaults for a specific template."""
    default = DEFAULT_TEMPLATE_SCHEDULES.get(template_id, {
        "enabled": True,
        "sendTime": "15:00",
        "timezone": "Asia/Beirut",
    })
    return deepcopy(default)

