"""Owner-facing status buckets. Runtime statuses stay unchanged."""

from __future__ import annotations

from typing import Final

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
