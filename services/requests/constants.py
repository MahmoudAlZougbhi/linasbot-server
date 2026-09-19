"""Customer Requests domain constants."""

from __future__ import annotations

from typing import Final

REQUEST_TYPES: Final[tuple[str, ...]] = ("ORDER", "APPOINTMENT", "OTHER", "HUMAN")
MAX_RULES_PER_REQUEST_TYPE: Final[int] = 10
# Board/persist path. HUMAN is a Live Chat handoff, never a Requests card.
PERSISTABLE_REQUEST_TYPES: Final[tuple[str, ...]] = ("ORDER", "APPOINTMENT", "OTHER")

STATUSES: Final[tuple[str, ...]] = (
    "NEW",
    "IN_REVIEW",
    "WAITING_FOR_CUSTOMER",
    "CONFIRMED",
    "READY",
    "COMPLETED",
    "CANCELLED",
)

SOURCE_CHANNEL_INSTAGRAM_DM: Final[str] = "instagram_dm"
SOURCE_CHANNEL_FACEBOOK_MESSENGER: Final[str] = "facebook_messenger"
SOURCE_CHANNEL_WHATSAPP_CLOUD: Final[str] = "whatsapp_cloud"
SOURCE_CHANNEL_COMMENT_LINKED_DM: Final[str] = "comment_linked_dm"
SOURCE_CHANNEL_WEB_CHAT: Final[str] = "web_chat"

SOURCE_CHANNELS: Final[tuple[str, ...]] = (
    SOURCE_CHANNEL_INSTAGRAM_DM,
    SOURCE_CHANNEL_FACEBOOK_MESSENGER,
    SOURCE_CHANNEL_WHATSAPP_CLOUD,
    SOURCE_CHANNEL_COMMENT_LINKED_DM,
    SOURCE_CHANNEL_WEB_CHAT,
)

EVENT_MANUAL_PAUSE: Final[str] = "manual_pause"
EVENT_MANUAL_RESUME: Final[str] = "manual_resume"
EVENT_NOTIFICATION_SENT: Final[str] = "notification_sent"
EVENT_NOTIFICATION_FAILED: Final[str] = "notification_failed"
EVENT_DELIVERY_BLOCKED: Final[str] = "DELIVERY_BLOCKED_BY_PLATFORM"

NOTIFICATION_STATUSES: Final[tuple[str, ...]] = (
    "none",
    "pending",
    "sent",
    "failed",
    "blocked",
)

# CM section key (filesystem draft → publish). Not active until published.
CM_SECTION_REQUESTS_APPOINTMENTS: Final[str] = "requests_appointments"

# Permission keys (must stay mirrored in mobile/web PERMISSION_KEYS).
PERM_REQUESTS: Final[str] = "requests"
PERM_REQUESTS_MANAGE: Final[str] = "requestsManage"
PERM_REQUESTS_NOTIFY: Final[str] = "requestsNotify"
PERM_REQUESTS_MANUAL_CHAT: Final[str] = "requestsManualChat"
PERM_REQUESTS_SENSITIVE: Final[str] = "requestsSensitive"

# Product UI buckets used by Mobile Requests. Internal statuses remain the SoT.
STATUS_BUCKET: Final[dict[str, str]] = {
    "NEW": "new",
    "IN_REVIEW": "in_progress",
    "WAITING_FOR_CUSTOMER": "in_progress",
    "CONFIRMED": "in_progress",
    "READY": "in_progress",
    "COMPLETED": "done",
    "CANCELLED": "cancelled",
}

BUCKET_LABEL: Final[dict[str, str]] = {
    "new": "New",
    "in_progress": "In Progress",
    "done": "Done",
    "cancelled": "Cancelled",
}


def status_bucket(status: str) -> str:
    return STATUS_BUCKET.get((status or "").strip().upper(), "in_progress")


def status_label(status: str) -> str:
    return BUCKET_LABEL[status_bucket(status)]


REQUEST_PERMISSION_KEYS: Final[tuple[str, ...]] = (
    PERM_REQUESTS,
    PERM_REQUESTS_MANAGE,
    PERM_REQUESTS_NOTIFY,
    PERM_REQUESTS_MANUAL_CHAT,
    PERM_REQUESTS_SENSITIVE,
)
