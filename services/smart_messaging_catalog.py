"""
Smart Messaging template catalog and scheduling defaults.
"""

from copy import deepcopy
from typing import Dict, Optional

# Product: "One Month Follow Up" is sent 17 days after the attended session (internal id twenty_day_followup; Meta: sent_17_days_after_last_session_new, 3 body variables).
TWENTY_DAY_FOLLOWUP_LOOKBACK_DAYS = 17

DAILY_TEMPLATE_IDS = (
    "reminder_24h",
    "post_session_feedback",
    "attended_yesterday",
    "missed_yesterday",
    "twenty_day_followup",
)

CAMPAIGN_TEMPLATE_IDS = (
    "missed_paused_appointment",
    "whatsapp_lead_no_booking",
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
        "name": "Post Session Feedback",
        "description": "Same calendar day, N hours after a completed (Done) visit — asks for 1–5 stars (Meta: thank_you_message_sent_after_session). Replies are logged in Smart Messaging → Session star ratings. Not the same flow as Attended Yesterday (next-day thank-you, no stars).",
    },
    "attended_yesterday": {
        "name": "Attended Yesterday",
        "description": "Next-day thank-you after a completed (Done) appointment. Separate from Post Session Feedback (same-day star rating).",
    },
    "missed_yesterday": {
        "name": "Missed Yesterday",
        "description": "Daily fixed-time follow-up for yesterday missed appointments (date=yesterday, status=Available).",
    },
    "twenty_day_followup": {
        "name": "One Month Follow Up",
        "description": "Daily fixed-time follow-up sent 17 days after last attended session. WhatsApp Meta template: sent_17_days_after_last_session_new — 3 body variables: customer_name, branch_name, service_name.",
    },
    "missed_paused_appointment": {
        "name": "Missed This Month",
        "description": "Manual BOC campaign for paused appointments. Outbound WhatsApp uses Meta template sent_for_pause (1 body variable: customer_name). Internal template key: missed_paused_appointment.",
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
    "post_session_feedback": {
        "enabled": True,
        "sendTime": "20:00",
        "timezone": "Asia/Beirut",
        "delayHours": 3,
    },
    "attended_yesterday": {
        "enabled": True,
        "sendTime": "11:00",
        "timezone": "Asia/Beirut",
    },
    "missed_yesterday": {
        "enabled": True,
        "sendTime": "10:00",
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

