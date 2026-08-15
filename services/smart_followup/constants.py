"""Smart Follow-Up constants and defaults."""

from __future__ import annotations

from datetime import timedelta
from typing import TypedDict

from services.requests.constants import (
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_WEB_CHAT,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
)

FOLLOWUP_CHANNELS = (
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_WEB_CHAT,
)

DEFAULT_CHANNELS_ENABLED: dict[str, bool] = {
    SOURCE_CHANNEL_WHATSAPP_CLOUD: True,
    SOURCE_CHANNEL_INSTAGRAM_DM: True,
    SOURCE_CHANNEL_FACEBOOK_MESSENGER: True,
    SOURCE_CHANNEL_WEB_CHAT: True,
}

ENTITLEMENT_KEY = "smart_followup"
BILLING_MODE_CUSTOMER_DIRECT = "customer_direct"
BILLING_MODE_SOLUTION_PARTNER = "solution_partner"
ALLOWED_BILLING_MODES = frozenset({BILLING_MODE_CUSTOMER_DIRECT, BILLING_MODE_SOLUTION_PARTNER})

GOALS = frozenset({"gentle_check_in", "offer_more_help", "politely_close"})


class DefaultStep(TypedDict):
    step_index: int
    enabled: bool
    delay_minutes: int
    goal: str


DEFAULT_STEPS: tuple[DefaultStep, ...] = (
    {"step_index": 1, "enabled": True, "delay_minutes": 30, "goal": "gentle_check_in"},
    {"step_index": 2, "enabled": True, "delay_minutes": 360, "goal": "offer_more_help"},
    {"step_index": 3, "enabled": True, "delay_minutes": 1200, "goal": "politely_close"},
)

CUSTOMER_SERVICE_WINDOW = timedelta(hours=24)
SAFETY_BUFFER = timedelta(minutes=12)
MAX_DELAY_MINUTES = 23 * 60
OPERATION_TYPE = "smart_followup"
DEFAULT_CHANNEL = SOURCE_CHANNEL_WHATSAPP_CLOUD
CLAIM_BATCH_SIZE = 25
CLAIM_STALE_SECONDS = 180
WORKER_ID_PREFIX = "sfu-worker"

TERMINAL_JOB_STATUSES = frozenset({"sent", "skipped", "cancelled", "failed", "reconciliation_required"})
ACTIVE_SEQUENCE_STATUSES = frozenset({"active"})

QUALIFYING_SOCIAL_ACTIONS = frozenset(
    {
        "answer_question",
        "normal_chat",
        "unknown_query",
        "provide_info",
        "tool_call",
        "check_customer_status",
        "confirm_appointment_reschedule",
        "ask_for_details_for_booking",
        "ask_for_service_type",
        "ask_for_details",
        "ask_for_tattoo_photo",
        "ask_clarification",
        "initial_greet_and_ask_gender",
        "ask_gender",
        "confirm_gender",
        "confirm_booking_details",
        "return_to_normal_chat",
    }
)
