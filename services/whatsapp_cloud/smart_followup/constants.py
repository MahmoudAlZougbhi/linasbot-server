"""Smart Follow-Up constants and defaults."""

from __future__ import annotations

from datetime import timedelta
from typing import TypedDict

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
OPERATION_TYPE = "whatsapp_smart_followup"
CLAIM_BATCH_SIZE = 25
CLAIM_STALE_SECONDS = 180
WORKER_ID_PREFIX = "sfu-worker"

TERMINAL_JOB_STATUSES = frozenset({"sent", "skipped", "cancelled", "failed", "reconciliation_required"})
ACTIVE_SEQUENCE_STATUSES = frozenset({"active"})
