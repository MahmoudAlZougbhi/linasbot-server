"""Save-time Luna search metadata (English-only, incremental, not a retrieval rewrite)."""

from __future__ import annotations

from services.search_metadata.errors import (
    METADATA_PREPARATION_CODE,
    METADATA_PREPARATION_MESSAGE,
    MetadataPreparationError,
)
from services.search_metadata.generate import (
    SearchMetadata,
    last_generate_stats,
    reset_metadata_generator,
    set_metadata_generator,
)

__all__ = [
    "METADATA_PREPARATION_CODE",
    "METADATA_PREPARATION_MESSAGE",
    "MetadataPreparationError",
    "SearchMetadata",
    "last_generate_stats",
    "reset_metadata_generator",
    "set_metadata_generator",
]
