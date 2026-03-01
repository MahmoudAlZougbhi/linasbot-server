"""
Smart Messaging template catalog and scheduling defaults.
"""

from copy import deepcopy
from typing import Dict, Optional


DAILY_TEMPLATE_IDS = (
    "reminder_24h",
    "post_session_feedback",
    "missed_yesterday",
    "attended_yesterday",
    "twenty_day_followup",
)

CAMPAIGN_TEMPLATE_IDS = (
    "missed_paused_appointment",
)

SUPPORTED_TEMPLATE_IDS = DAILY_TEMPLATE_IDS + CAMPAIGN_TEMPLATE_IDS

DEPRECATED_TEMPLATE_IDS = (
    "same_day_checkin",
    "no_show_followup",
)

LEGACY_TEMPLATE_ALIASES = {
    "one_month_followup": "twenty_day_followup",
    "missed_this_month": "missed_paused_appointment",
}

TEMPLATE_METADATA: Dict[str, Dict[str, str]] = {
    "reminder_24h": {
        "name": "24-Hour Reminder",
        "description": "Daily fixed-time reminder for tomorrow appointments.",
    },
    "post_session_feedback": {
        "name": "Post-Session Feedback",
        "description": "Daily fixed-time feedback request for attended today sessions.",
    },
    "missed_yesterday": {
        "name": "Missed Yesterday",
        "description": "Daily fixed-time follow-up for yesterday missed appointments.",
    },
    "attended_yesterday": {
        "name": "Attended Yesterday",
        "description": "Daily fixed-time thank-you/follow-up for yesterday attended appointments.",
    },
    "twenty_day_followup": {
        "name": "20-Day Follow-up",
        "description": "Daily fixed-time follow-up sent 20 days after last attended session.",
    },
    "missed_paused_appointment": {
        "name": "Missed Paused Appointment",
        "description": "Manual campaign template for paused appointments.",
    },
}

DEFAULT_TEMPLATE_SCHEDULES: Dict[str, Dict[str, object]] = {
    "reminder_24h": {
        "enabled": True,
        "sendTime": "15:00",
        "timezone": "Asia/Beirut",
    },
    "post_session_feedback": {
        "enabled": True,
        "sendTime": "20:00",
        "timezone": "Asia/Beirut",
    },
    "missed_yesterday": {
        "enabled": True,
        "sendTime": "10:00",
        "timezone": "Asia/Beirut",
    },
    "attended_yesterday": {
        "enabled": True,
        "sendTime": "21:00",
        "timezone": "Asia/Beirut",
    },
    "twenty_day_followup": {
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

