"""Compact internal search-metadata limits (token control)."""

from __future__ import annotations

AI_SEARCH_TITLE_MAX = 80
AI_SEARCH_DESCRIPTION_MAX = 180
AI_SEARCH_KEYWORDS_MAX = 8
AI_SEARCH_KEYWORD_MAX = 32

# Sections whose selectable items participate in Customer Reply routing.
METADATA_SECTIONS = frozenset(
    {
        "knowledge",
        "care",
        "faq",
        "services",
        "branches",
        "opening_hours",
        "dynamic_messages",
        "requests_appointments",
        "comments",
        "off_days",
    }
)

# Luna must see every title in these sections (not the first 80 only).
# Knowledge/services/faq stay pageable because they can be thousands of files.
LUNA_FULL_TITLE_SECTIONS = frozenset(
    {
        "requests_appointments",
        "comments",
        "branches",
        "opening_hours",
        "off_days",
        "dynamic_messages",
    }
)

ITEM_LIST_KEYS = ("items", "rules", "catalog")

META_FIELD_KEYS = frozenset(
    {
        "ai_search_title",
        "ai_search_description",
        "ai_search_keywords",
        "ai_search_title_normalized",
    }
)
