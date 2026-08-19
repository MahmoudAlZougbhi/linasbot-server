"""Save-time Luna search metadata (English-only, incremental, not a retrieval rewrite)."""

from __future__ import annotations

from services.search_metadata.generate import (
    SearchMetadata,
    last_generate_stats,
    reset_metadata_generator,
    set_metadata_generator,
)

__all__ = [
    "SearchMetadata",
    "last_generate_stats",
    "reset_metadata_generator",
    "set_metadata_generator",
]
