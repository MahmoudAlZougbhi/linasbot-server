"""DEAD Luna naming shim — title view helpers only. Prefer title_fields.

Customer Brain does not use a Luna generative retrieval engine. This module
keeps import paths for search-metadata title fields.
"""

from __future__ import annotations

from services.search_metadata.title_fields import (  # noqa: F401
    original_title_of,
    retrieval_title_fields,
)

DEAD_LUNA_ENGINE = True


def luna_title_fields(raw: dict) -> dict[str, str]:
    """Deprecated alias for retrieval_title_fields."""
    return retrieval_title_fields(raw)
