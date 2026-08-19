"""User-facing metadata preparation failure (no model/key details)."""

from __future__ import annotations

METADATA_PREPARATION_CODE = "METADATA_PREPARATION_FAILED"
METADATA_PREPARATION_MESSAGE = (
    "Could not prepare this content for AI. Your changes were not saved. Please try again."
)


class MetadataPreparationError(Exception):
    """Save must stop: do not write or activate a version without ready metadata."""

    def __init__(self, message: str = METADATA_PREPARATION_MESSAGE) -> None:
        super().__init__(message)
        self.code = METADATA_PREPARATION_CODE
        self.user_message = message
