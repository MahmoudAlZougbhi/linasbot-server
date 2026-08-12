"""
Smart Messaging Service
Implements requirement #11 from project specifications

Templates/queue/appointments mixins; deliver/firestore helpers (LOC split).
"""

from __future__ import annotations

from typing import Any

from services.smart_messaging_appointments import SmartMessagingAppointmentsMixin
from services.smart_messaging_deliver import (  # noqa: F401
    deliver_scheduled_smart_whatsapp,
    message_type_names,
)
from services.smart_messaging_firestore import get_sent_smart_messages_from_firestore  # noqa: F401
from services.smart_messaging_queue import SmartMessagingQueueMixin
from services.smart_messaging_templates import SmartMessagingTemplatesMixin
from storage.persistent_storage import (
    APP_SETTINGS_FILE,
    MESSAGE_TEMPLATES_FILE,
    PENDING_SMART_MESSAGES_FILE,
    SENT_SMART_MESSAGES_FILE,
    SERVICE_TEMPLATE_MAPPING_FILE,
    ensure_dirs,
)

# Preview mode blocks automatic sends. No metadata source may bypass approval.
AUTOMATED_PREVIEW_EXEMPT_METADATA_SOURCES: frozenset[str] = frozenset()


class SmartMessagingService(
    SmartMessagingTemplatesMixin,
    SmartMessagingQueueMixin,
    SmartMessagingAppointmentsMixin,
):
    """
    Handles automated messaging:
    - 24h appointment reminders
    - Same-day check-ins
    - Post-session feedback
    - No-show follow-ups
    - 1-month follow-ups
    """

    # If a message stays in status "sending" longer than this (crash, timeout, killed worker),
    # reset to "scheduled" so the monitor can retry. Otherwise it never sends again.
    STUCK_SENDING_MAX_AGE_SECONDS = 600.0

    SENT_MESSAGES_FILE = str(SENT_SMART_MESSAGES_FILE)
    QUEUE_FILE = str(PENDING_SMART_MESSAGES_FILE)

    def __init__(self) -> None:
        ensure_dirs()
        self.templates_file = str(MESSAGE_TEMPLATES_FILE)
        self.settings_file = str(APP_SETTINGS_FILE)
        self.mapping_file = str(SERVICE_TEMPLATE_MAPPING_FILE)
        self.message_templates = self._load_templates()
        self.scheduled_messages: dict[str, dict[str, Any]] = {}
        self.sent_messages_log: list[dict[str, Any]] = []
        self._load_sent_messages()
        self._load_pending_queue()


# Global instance
smart_messaging = SmartMessagingService()
