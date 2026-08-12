"""Customer Requests domain constants."""

from __future__ import annotations

from typing import Final

REQUEST_TYPES: Final[tuple[str, ...]] = ("ORDER", "APPOINTMENT", "OTHER")

STATUSES: Final[tuple[str, ...]] = (
    "NEW",
    "IN_REVIEW",
    "WAITING_FOR_CUSTOMER",
    "CONFIRMED",
    "READY",
    "COMPLETED",
    "CANCELLED",
)

SOURCE_CHANNELS: Final[tuple[str, ...]] = (
    "instagram_dm",
    "facebook_messenger",
    "whatsapp_cloud",
    "comment_linked_dm",
)

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

REQUEST_PERMISSION_KEYS: Final[tuple[str, ...]] = (
    PERM_REQUESTS,
    PERM_REQUESTS_MANAGE,
    PERM_REQUESTS_NOTIFY,
    PERM_REQUESTS_MANUAL_CHAT,
    PERM_REQUESTS_SENSITIVE,
)
